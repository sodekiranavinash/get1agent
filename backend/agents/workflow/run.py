"""Run one workflow: build the orchestrator and stream normalized frames.

Mirrors ``agentflow.run``: one OTel trace per run, one persisted conversation
turn, and the same best-effort persistence guarantees. The orchestration itself
is delegated to Strands (``Graph`` / ``Swarm``); this module only assembles the
agents, forwards their events and derives the final answer.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator

from agentflow.config import load_config
from agentflow.conversations import persist_turn
from agentflow.events import accumulated_usage
from agentflow.hitl import (
    interrupt_responses,
    pending_interrupt_responses,
    question_from_interrupt,
)
from agentflow.identity import resolve_user_id
from agentflow.observability import flush, run_trace, trace_identity
from data.client import now_iso
from data.repositories import quotas
from data.repositories import workflows as workflows_repo

from workflow.build import (
    HOST_NODE_ID,
    HOST_SYNTH_NODE_ID,
    build_workflow,
)
from workflow.events import normalize
from workflow.store import load_workflow


def _conversation_id(payload: dict[str, Any], context: Any) -> str:
    for key in ("conversationId", "sessionId"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return str(getattr(context, "session_id", "") or "default")


def _input_text(payload: dict[str, Any], workflow_config: dict[str, Any]) -> str:
    text = payload.get("input")
    if text is None:
        text = payload.get("prompt")
    if text is None:
        text = (workflow_config.get("input") or {}).get("query")
    return str(text or "").strip()


def _node_payload(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shape the workflow's node metadata for the `workflow` event.

    Same shape the client's ``WorkflowRunNodeMeta`` expects: the node id is
    ``id`` (every other frame uses ``nodeId``), and role/stage tell the client
    which host is which so the two graph hosts don't read as duplicates.
    """
    return [
        {
            "id": node["nodeId"],
            "name": node.get("agentName") or node["nodeId"],
            "agentName": node.get("agentName") or node["nodeId"],
            "model": node.get("model"),
            "role": node.get("role"),
            "stage": node.get("stage"),
        }
        for node in nodes
    ]


def _sink_nodes(workflow_config: dict[str, Any]) -> list[str]:
    nodes = workflow_config.get("nodes") or []
    agent_ids = {
        str(node.get("id"))
        for node in nodes
        if isinstance(node, dict) and node.get("type") == "agent"
    }
    has_out: set[str] = set()
    for edge in workflow_config.get("edges") or []:
        source = str(edge.get("source"))
        target = str(edge.get("target"))
        if source in agent_ids and target in agent_ids:
            has_out.add(source)
    return [node_id for node_id in agent_ids if node_id not in has_out]


def _final_answer(
    mode: str,
    answer_node_id: str,
    sinks: list[str],
    text_by_node: dict[str, str],
    order: list[str],
) -> str:
    # The host owns the final answer: the swarm host or the graph synthesizer.
    if text_by_node.get(answer_node_id):
        return text_by_node[answer_node_id].strip()
    if mode == "graph":
        parts = [text_by_node[node_id].strip() for node_id in sinks if text_by_node.get(node_id)]
        if parts:
            return "\n\n".join(parts)
    for node_id in reversed(order):
        if text_by_node.get(node_id):
            return text_by_node[node_id].strip()
    return ""


async def run_workflow_stream(payload: Any, context: Any) -> AsyncIterator[dict[str, Any]]:
    payload = payload if isinstance(payload, dict) else {}
    run_id = uuid.uuid4().hex

    config = None
    user_id: str | None = None
    workflow_id = ""
    workflow_name = ""
    conversation_id: str | None = None
    mode = "graph"
    answer_node_id = HOST_NODE_ID
    original_input = ""
    started_at = now_iso()
    recorded: list[dict[str, Any]] = []
    status = "completed"
    raw_hitl = payload.get("humanInLoop")
    human_in_loop: bool | None = raw_hitl if isinstance(raw_hitl, bool) else None
    resume_responses = interrupt_responses(payload)
    resume_run_id = str(payload.get("resumeRunId") or "").strip() or None
    pending_question = payload.get("pendingQuestion")
    pending_question = pending_question if isinstance(pending_question, dict) else None
    awaiting_input = False
    trace = None
    observation: Any = None
    trace_id: str | None = None
    trace_url: str | None = None
    text_by_node: dict[str, str] = {}
    order: list[str] = []
    node_meta: dict[str, dict[str, Any]] = {}
    result_usage: dict[str, Any] = {}
    spend_model = ""
    sinks: list[str] = []

    try:
        config = load_config()
        user_id = resolve_user_id(payload, context)
        workflow_id = str(payload.get("workflowId") or "").strip()
        if not workflow_id:
            raise ValueError("workflowId is required")

        # Deterministic tool-call policy (AgentCore Policy), shared by every node.
        from agentflow.memory import build_guard
        from core import policy

        guard = build_guard(policy.build_evaluator())

        workflow = load_workflow(user_id, workflow_id)
        workflow_config = workflow.get("config") or {}
        workflow_name = str(workflow.get("name") or "")
        mode = str(workflow_config.get("mode") or "graph")
        answer_node_id = HOST_SYNTH_NODE_ID if mode == "graph" else HOST_NODE_ID
        conversation_id = _conversation_id(payload, context)
        user_input = _input_text(payload, workflow_config)
        original_input = user_input
        if not user_input and not resume_responses:
            raise ValueError("input is required")
        if resume_responses and pending_question:
            recorded.append({"type": "question", **pending_question})

        # Budget gate: a workflow's host runs on the platform gateway, so the
        # same application budget applies.
        quotas.check_budget(user_id)

        yield {
            "type": "run.started",
            "runId": run_id,
            "workflowId": workflow_id,
            "sessionId": conversation_id,
            "mode": mode,
        }

        counter: dict[str, int] = {"n": 0}
        # Per-run style overrides from the chat composer apply to the host only.
        host_overrides = {
            "answerMode": str(payload.get("answerMode") or "").strip(),
            "reasoning": str(payload.get("reasoning") or "").strip(),
        }
        # Per-run agent selection from the chat run settings: None means "use the
        # workflow's saved agents".
        requested_agents = payload.get("agentIds")
        agent_ids = (
            [str(value) for value in requested_agents if str(value or "").strip()]
            if isinstance(requested_agents, list)
            else None
        )
        orchestrator, mode, nodes = build_workflow(
            config,
            user_id,
            conversation_id,
            workflow_config,
            counter,
            host_overrides,
            agent_ids,
            # On a resume the host must keep the `ask_user` tool so the paused
            # call can replay, even if auto-approve was turned on afterwards —
            # but a *new* question is refused so the run can't loop.
            human_in_loop or bool(resume_responses),
            guard,
            allow_new_questions=not bool(resume_responses),
        )
        if not any(node["role"] == "agent" for node in nodes):
            raise ValueError("This workflow has no runnable agents")
        for node in nodes:
            node_meta[node["nodeId"]] = {
                "agentName": node["agentName"],
                "model": node["model"],
            }
        sinks = _sink_nodes(workflow_config)
        spend_model = next(
            (str(node["model"]) for node in nodes if node.get("role") == "host"), ""
        )

        yield {
            "type": "workflow",
            "mode": mode,
            "nodes": _node_payload(nodes),
        }

        trace = run_trace(
            f"workflow:{workflow_name or workflow_id}",
            input=user_input,
            user_id=user_id,
            session_id=conversation_id,
            tags=["workflow", mode, *(workflow_name and [workflow_name] or [])],
            metadata={
                "workflowId": workflow_id,
                "workflowName": workflow_name,
                "mode": mode,
                "runId": run_id,
                "conversationId": conversation_id,
            },
        )
        observation = trace.__enter__()

        # Recover a workflow left paused at a host question when a new message
        # arrives instead of an answer.
        if not resume_responses:
            recovered = pending_interrupt_responses(orchestrator, user_input)
            if recovered:
                resume_responses = recovered

        seen_questions: set[str] = set()
        async for raw in orchestrator.stream_async(resume_responses or user_input):
            for frame in normalize(raw, node_meta):
                ftype = frame.get("type")
                if ftype == "question":
                    question_id = str(frame.get("questionId") or "")
                    if question_id and question_id in seen_questions:
                        continue
                    if question_id:
                        seen_questions.add(question_id)
                    awaiting_input = True
                    status = "awaiting_input"
                    recorded.append(frame)
                    yield frame
                    continue
                if ftype in ("node.started", "node.completed"):
                    # Stamp the frame at emit time so a replayed transcript keeps
                    # accurate per-node durations instead of all ~0ms.
                    frame["at"] = int(time.time() * 1000)
                if ftype == "node.stream":
                    inner = frame.get("event") or {}
                    if inner.get("type") == "text":
                        node_id = str(frame.get("nodeId") or "")
                        text_by_node[node_id] = text_by_node.get(node_id, "") + str(
                            inner.get("data") or ""
                        )
                        # An intermediate agent's text is input for the host, not
                        # output for the user: never stream it. Only the final
                        # answer host streams, so the answer types out live.
                        if node_id != answer_node_id:
                            continue
                elif ftype == "node.completed":
                    node_id = str(frame.get("nodeId") or "")
                    if node_id not in order:
                        order.append(node_id)
                recorded.append(frame)
                yield frame

            if isinstance(raw, dict) and raw.get("type") == "multiagent_result":
                result = raw.get("result")
                result_usage = accumulated_usage(
                    getattr(result, "accumulated_usage", None)
                ) or result_usage
                # A node (the host) paused for the user's answer: surface the
                # question(s) so the client can resume the same workflow.
                for interrupt in getattr(result, "interrupts", None) or []:
                    question = question_from_interrupt(interrupt)
                    if not question:
                        continue
                    question_id = str(question.get("questionId") or "")
                    if question_id and question_id in seen_questions:
                        continue
                    if question_id:
                        seen_questions.add(question_id)
                    frame = {"type": "question", **question}
                    awaiting_input = True
                    status = "awaiting_input"
                    recorded.append(frame)
                    yield frame

        answer = _final_answer(mode, answer_node_id, sinks, text_by_node, order)
        if observation is not None:
            try:
                trace_id, trace_url = trace_identity(observation)
            except Exception:  # noqa: BLE001 - tracing must never break a run
                pass
        if trace_id or trace_url:
            trace_event = {"type": "trace", "traceId": trace_id, "traceUrl": trace_url}
            recorded.append(trace_event)
            yield trace_event

        # A paused run has no final answer yet; the resumed run completes it.
        if not awaiting_input:
            completed = {
                "type": "run.completed",
                "answer": answer,
                "usage": result_usage,
            }
            recorded.append(completed)
            yield completed

        if observation is not None:
            observation.update(output=answer)

    except Exception as exc:  # noqa: BLE001 - surface any failure to the client
        status = "error"
        failure = {"type": "run.error", "message": str(exc)}
        recorded.append(failure)
        if observation is not None:
            try:
                observation.update(level="ERROR", status_message=str(exc))
            except Exception:  # noqa: BLE001
                pass
        yield failure
    finally:
        if trace is not None:
            if trace_id is None and trace_url is None:
                try:
                    trace_id, trace_url = trace_identity(observation)
                except Exception:  # noqa: BLE001
                    pass
            try:
                trace.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
        try:
            if (
                config is not None
                and user_id
                and workflow_id
                and conversation_id is not None
            ):
                answer = _final_answer(mode, answer_node_id, sinks, text_by_node, order)
                persist_turn(
                    config,
                    user_id,
                    conversation_id,
                    {
                        "runId": run_id,
                        "question": original_input,
                        "agentId": workflow_id,
                        "agentName": workflow_name,
                        "targetType": "workflow",
                        "mode": mode,
                        "startedAt": started_at,
                        "completedAt": now_iso(),
                        "status": status,
                        "traceId": trace_id,
                        "traceUrl": trace_url,
                        "events": recorded,
                    },
                    run_id=run_id,
                    preview=answer[:280],
                    trace_id=trace_id,
                    trace_url=trace_url,
                    replace_run_id=resume_run_id,
                )
        except Exception:  # noqa: BLE001 - persistence never changes the outcome
            pass
        # Stamp the workflow's recency for the store list (best-effort).
        try:
            if user_id and workflow_id:
                workflows_repo.mark_run(user_id, workflow_id, run_at=now_iso())
        except Exception:  # noqa: BLE001
            pass
        # Charge the run to the user's application budget (best-effort).
        try:
            if user_id and result_usage:
                quotas.charge_usage(
                    user_id,
                    model=spend_model,
                    input_tokens=result_usage.get("inputTokens") or 0,
                    output_tokens=result_usage.get("outputTokens") or 0,
                )
        except Exception:  # noqa: BLE001 - accounting never breaks a run
            pass
        flush()
