"""Build and persist a Langfuse-style trace for one agent run (AWS-native).

The runtime already streams normalized frames and records them for the
transcript. This module projects those frames into a **trace + observations**
tree (the Langfuse data model) with real per-observation timing, so the traces
page can render a rich explorer instead of a coarse X-Ray waterfall:

* the full tree is written to S3 (``retrieval.layout.trace_key``) — inputs,
  outputs, arguments and tool results stay here, never in DynamoDB;
* a small index item goes to DynamoDB (``data.repositories.traces``) so the
  list/filter view is one Query with no S3 reads;
* ``agentflow.observability`` still exports the OpenTelemetry spans that
  CloudWatch GenAI Observability reads — this store is additive, not a
  replacement.

The hierarchy mirrors how a run actually executes, so the tree reads in order:

    run (SPAN)
      ├─ skills / attachments (EVENT)
      ├─ planner (GENERATION)          the plan
      │    ├─ tool (TOOL)              each planned step
      │    └─ tool (TOOL)
      └─ answer (GENERATION)           the final response

Everything is best-effort: a trace-store failure must never fail a run.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from agentflow.config import RuntimeConfig
from core.storage import Storage
from data.repositories import traces as traces_repo
from retrieval.layout import trace_key

# A single observation must not balloon the S3 object; clip the long fields.
MAX_FIELD_CHARS = 40_000
# How many observations one trace may carry (drop the rest, count is kept).
MAX_OBSERVATIONS = 400


def _warn(message: str, exc: BaseException) -> None:
    print(
        json.dumps({"level": "warning", "message": message, "error": str(exc)}),
        flush=True,
    )


def _clip(value: Any, limit: int = MAX_FIELD_CHARS) -> Any:
    """Bound a field for storage without losing its type when small."""
    if value is None:
        return None
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit]
    try:
        text = json.dumps(value, default=str)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) <= limit:
        return value
    return text[:limit]


def _parse_ms(value: Any) -> int | None:
    """ISO timestamp -> epoch milliseconds (None when unparseable)."""
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except (TypeError, ValueError):
        return None


def _event_at(event: dict[str, Any], fallback: int | None) -> int | None:
    value = event.get("_at")
    return int(value) if isinstance(value, (int, float)) else fallback


def _observation_id(trace_id: str, kind: str, key: str) -> str:
    return f"{trace_id}-{kind}-{key}"


def _normalize_status(status: str) -> str:
    return "ok" if status in ("completed", "ok", "") else str(status)


def _cost_micro_usd(model: str, usage: dict[str, Any]) -> int:
    try:
        from core import usage as usage_mod

        return int(
            usage_mod.cost_micro_usd(
                model,
                int(usage.get("inputTokens") or 0),
                int(usage.get("outputTokens") or 0),
            )
        )
    except Exception:  # noqa: BLE001 - pricing must never break a trace
        return 0


def _observation_cost(model: Any, usage: Any) -> int:
    """Per-observation cost in micro-USD (0 when the span carries no usage)."""
    if not isinstance(usage, dict) or not model:
        return 0
    return _cost_micro_usd(str(model), usage)


def _extract_retrieval(output: Any) -> dict[str, Any] | None:
    """Pull the retrieval detail out of a knowledge tool's result payload.

    The knowledge MCP returns ``chunks[]`` (with vector/lexical/RRF/rerank
    scores) plus a ``meta`` block of per-leg timings. Surfacing it as structured
    metadata is what lets the viewer render a real retriever span instead of
    raw JSON.
    """
    if not isinstance(output, dict):
        return None
    chunks = output.get("chunks")
    if not isinstance(chunks, list):
        chunks = output.get("results") if isinstance(output.get("results"), list) else None
    meta = output.get("meta") if isinstance(output.get("meta"), dict) else None
    sources = output.get("sources") if isinstance(output.get("sources"), list) else None
    if chunks is None and meta is None and sources is None:
        return None
    detail: dict[str, Any] = {}
    if chunks is not None:
        detail["chunks"] = [
            {
                key: chunk.get(key)
                for key in (
                    "chunkId",
                    "documentId",
                    "knowledgeBaseId",
                    "fileName",
                    "page",
                    "vectorScore",
                    "lexicalScore",
                    "rrfScore",
                    "rerankScore",
                    "score",
                )
                if isinstance(chunk, dict) and chunk.get(key) is not None
            }
            for chunk in chunks[:50]
            if isinstance(chunk, dict)
        ]
        detail["chunkCount"] = len(chunks)
    if meta is not None:
        detail["meta"] = {
            key: meta.get(key)
            for key in (
                "embedMs",
                "searchMs",
                "rerankMs",
                "reranked",
                "rerankMode",
                "candidateCount",
                "returned",
                "topK",
            )
            if meta.get(key) is not None
        }
    if sources is not None:
        detail["sourceCount"] = len(sources)
    return detail or None


def _planner_model() -> str:
    return (os.environ.get("AGENT_PLANNER_MODEL") or "").strip()


def build_trace(
    *,
    trace_id: str,
    run_id: str,
    user_id: str,
    agent_id: str,
    agent_name: str,
    model: str,
    provider: str | None,
    conversation_id: str | None,
    question: str,
    answer: str,
    status: str,
    started_at: str,
    ended_at: str,
    events: list[dict[str, Any]],
    usage: dict[str, Any] | None,
    tags: list[str],
    system_prompt_text: str | None = None,
) -> dict[str, Any]:
    """Project a run's recorded frames into a trace + observation tree."""
    trace_id = str(trace_id)
    start_ms = _parse_ms(started_at)
    end_ms = _parse_ms(ended_at)
    latency_ms = (
        max(0, end_ms - start_ms)
        if start_ms is not None and end_ms is not None
        else None
    )

    observations: list[dict[str, Any]] = []
    root_id = _observation_id(trace_id, "run", "root")
    planner_id = _observation_id(trace_id, "planner", "0")
    answer_id = _observation_id(trace_id, "gen", "answer")
    pending_tools: dict[str, dict[str, Any]] = {}
    tool_order: list[str] = []
    error_message: str | None = None
    has_plan = False
    first_text_at: int | None = None
    last_tool_end: int | None = None
    error_detail: dict[str, Any] = {}
    system_prompt = str(system_prompt_text or "")
    cursor = start_ms

    def add(observation: dict[str, Any]) -> None:
        if len(observations) < MAX_OBSERVATIONS:
            observations.append(observation)

    for event in events:
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        at = _event_at(event, cursor)
        if at is not None:
            cursor = at

        if kind == "plan":
            has_plan = True
            add(
                {
                    "id": planner_id,
                    "parentObservationId": root_id,
                    "type": "GENERATION",
                    "name": "planner",
                    "model": _planner_model() or None,
                    "startTime": at,
                    "endTime": at,
                    "durationMs": 0,
                    "level": "DEFAULT",
                    "input": _clip(question),
                    "output": _clip(
                        {
                            "understanding": event.get("understanding"),
                            "subQueries": event.get("subQueries"),
                        }
                    ),
                    "usage": None,
                    "metadata": {"kind": "plan"},
                }
            )
        elif kind in ("tool.start", "tool.input", "tool.stream", "tool.result"):
            tool_use_id = str(event.get("toolUseId") or f"tool-{len(tool_order)}")
            tool = pending_tools.get(tool_use_id)
            if tool is None:
                tool = {
                    "id": _observation_id(trace_id, "tool", tool_use_id),
                    # Tools are the plan's steps: nest them under the planner so
                    # the tree reads plan -> tool, not answer -> tool.
                    "parentObservationId": planner_id if has_plan else root_id,
                    "type": "TOOL",
                    "name": str(event.get("name") or "tool"),
                    "startTime": at,
                    "endTime": None,
                    "durationMs": None,
                    "level": "DEFAULT",
                    "input": None,
                    "output": None,
                    "usage": None,
                    "metadata": {},
                }
                pending_tools[tool_use_id] = tool
                tool_order.append(tool_use_id)
            if event.get("name"):
                tool["name"] = str(event["name"])
            if kind in ("tool.start", "tool.input") and event.get("input") is not None:
                tool["input"] = _clip(event.get("input"))
            if kind == "tool.result":
                tool["endTime"] = at
                tool["output"] = _clip(event.get("data"))
                tool["durationMs"] = (
                    max(0, at - tool["startTime"])
                    if at is not None and tool.get("startTime") is not None
                    else None
                )
                tool["level"] = (
                    "ERROR" if str(event.get("status") or "") == "error" else "DEFAULT"
                )
                if event.get("statusMessage"):
                    tool["statusMessage"] = _clip(event.get("statusMessage"), 2000)
                if event.get("sources"):
                    tool["metadata"]["sources"] = _clip(event.get("sources"))
                # This is a retriever call: keep its scores/timings structured.
                retrieval = _extract_retrieval(event.get("data"))
                if retrieval:
                    tool["metadata"]["retrieval"] = _clip(retrieval)
            if tool.get("endTime") is not None:
                last_tool_end = max(last_tool_end or 0, int(tool["endTime"]))
        elif kind == "skills":
            names = [str(s.get("name")) for s in (event.get("skills") or []) if s.get("name")]
            add(
                {
                    "id": _observation_id(trace_id, "event", "skills"),
                    "parentObservationId": root_id,
                    "type": "EVENT",
                    "name": "skills",
                    "startTime": at,
                    "endTime": at,
                    "durationMs": 0,
                    "level": "DEFAULT",
                    "input": None,
                    "output": names,
                    "usage": None,
                    "metadata": {"kind": "skills"},
                }
            )
        elif kind == "attachments":
            files = [str(f.get("fileName")) for f in (event.get("files") or []) if f.get("fileName")]
            add(
                {
                    "id": _observation_id(trace_id, "event", "attachments"),
                    "parentObservationId": root_id,
                    "type": "EVENT",
                    "name": "attachments",
                    "startTime": at,
                    "endTime": at,
                    "durationMs": 0,
                    "level": "DEFAULT",
                    "input": None,
                    "output": files,
                    "usage": None,
                    "metadata": {"kind": "attachments"},
                }
            )
        elif kind == "question":
            add(
                {
                    "id": _observation_id(trace_id, "event", "question"),
                    "parentObservationId": root_id,
                    "type": "EVENT",
                    "name": "user_question",
                    "startTime": at,
                    "endTime": at,
                    "durationMs": 0,
                    "level": "DEFAULT",
                    "input": _clip(event.get("question")),
                    "output": _clip(event.get("answer")),
                    "usage": None,
                    "metadata": {"options": event.get("options") or []},
                }
            )
        elif kind == "context":
            add(
                {
                    "id": _observation_id(trace_id, "event", "context"),
                    "parentObservationId": root_id,
                    "type": "EVENT",
                    "name": "context",
                    "startTime": at,
                    "endTime": at,
                    "durationMs": 0,
                    "level": "DEFAULT",
                    "input": None,
                    "output": None,
                    "usage": None,
                    "metadata": {
                        "usedTokens": event.get("usedTokens"),
                        "limitTokens": event.get("limitTokens"),
                        "ratio": event.get("ratio"),
                        "breakdown": event.get("breakdown"),
                    },
                }
            )
        elif kind == "text":
            if first_text_at is None:
                first_text_at = at
        elif kind == "run.error":
            error_message = str(event.get("message") or event.get("error") or "run failed")
            error_meta = {
                "kind": str(event.get("errorKind") or ""),
                "detail": str(event.get("detail") or ""),
                "stack": str(event.get("stack") or ""),
            }
            error_meta = {key: value for key, value in error_meta.items() if value}
            error_detail = error_meta
            if error_meta:
                add(
                    {
                        "id": _observation_id(trace_id, "event", "error"),
                        "parentObservationId": root_id,
                        "type": "EVENT",
                        "name": "error",
                        "startTime": at,
                        "endTime": at,
                        "durationMs": 0,
                        "level": "ERROR",
                        "statusMessage": error_message,
                        "input": None,
                        "output": None,
                        "usage": None,
                        "metadata": error_meta,
                    }
                )

    # Finish any tool that never produced a result (errored/aborted runs).
    for tool in pending_tools.values():
        if tool["endTime"] is None:
            tool["endTime"] = end_ms
            if tool["startTime"] is not None and end_ms is not None:
                tool["durationMs"] = max(0, end_ms - tool["startTime"])
            tool["level"] = "ERROR"
            if end_ms is not None:
                last_tool_end = max(last_tool_end or 0, end_ms)

    for tool_use_id in tool_order:
        add(pending_tools[tool_use_id])

    usage = usage or {}

    # The final answer generation: after planning/tools, before the run ends.
    answer_start = first_text_at or last_tool_end or start_ms
    add(
        {
            "id": answer_id,
            "parentObservationId": root_id,
            "type": "GENERATION",
            "name": "answer",
            "model": model or None,
            "startTime": answer_start,
            "endTime": end_ms,
            "durationMs": (
                max(0, end_ms - answer_start)
                if end_ms is not None and answer_start is not None
                else latency_ms
            ),
            "level": "ERROR" if error_message else "DEFAULT",
            "statusMessage": error_message,
            "input": _clip(question),
            "output": _clip(answer),
            "usage": usage or None,
            "costMicroUsd": _observation_cost(model, usage) if usage else 0,
            "metadata": {"provider": provider} if provider else {},
        }
    )

    # The root span is the run itself; it sorts first and owns every stage.
    observations.insert(
        0,
        {
            "id": root_id,
            "parentObservationId": None,
            "type": "SPAN",
            "name": agent_name or agent_id or "run",
            "model": model or None,
            "startTime": start_ms,
            "endTime": end_ms,
            "durationMs": latency_ms,
            "level": "ERROR" if error_message else "DEFAULT",
            "statusMessage": None,
            "input": None,
            "output": None,
            "usage": usage or None,
            "costMicroUsd": _observation_cost(model, usage) if usage else 0,
            "metadata": {
                "kind": "run",
                "agentId": agent_id,
                "runId": run_id,
                "conversationId": conversation_id,
                "provider": provider,
                "tags": [str(tag) for tag in (tags or [])],
                "systemPrompt": _clip(system_prompt) if system_prompt else None,
                "systemPromptTokens": None,
                **({"errorDetail": error_detail} if error_detail else {}),
            },
        },
    )

    normalized_status = _normalize_status(status)
    type_counts: dict[str, int] = {}
    error_count = 0
    for observation in observations:
        obs_type = str(observation.get("type") or "SPAN")
        type_counts[obs_type] = type_counts.get(obs_type, 0) + 1
        if observation.get("level") == "ERROR":
            error_count += 1
    stage_latency_ms = 0
    for observation in observations:
        if observation.get("id") != root_id:
            stage_latency_ms += int(observation.get("durationMs") or 0)
    return {
        "id": trace_id,
        "traceId": trace_id,
        "name": f"agent:{agent_name or agent_id or 'run'}",
        "userId": user_id,
        "sessionId": conversation_id,
        "conversationId": conversation_id,
        "runId": run_id,
        "agentId": agent_id,
        "agentName": agent_name,
        "model": model,
        "provider": provider,
        "tags": [str(tag) for tag in (tags or [])],
        "status": normalized_status,
        "level": "ERROR" if error_message else "DEFAULT",
        "statusMessage": error_message,
        "startedAt": started_at,
        "endedAt": ended_at,
        "latencyMs": latency_ms,
        "input": question,
        "output": answer,
        "usage": usage,
        "costMicroUsd": _cost_micro_usd(model, usage),
        "observationCount": len(observations),
        "summary": {
            "observationCount": len(observations),
            "errorCount": error_count,
            "typeCounts": type_counts,
            "totalStageLatencyMs": stage_latency_ms,
            "hasSystemPrompt": bool(system_prompt),
        },
        "createdAt": started_at,
        "observations": observations,
    }


def persist_trace(config: RuntimeConfig, user_id: str, trace: dict[str, Any]) -> None:
    """Write the full tree to S3 and the small index item to DynamoDB."""
    if not config.s3_bucket or not user_id or not trace:
        return
    trace_id = str(trace.get("traceId") or "")
    if not trace_id:
        return
    try:
        Storage().put_json(trace_key(user_id, trace_id), trace)
    except Exception as exc:  # noqa: BLE001 - never fail a run on the tree
        _warn("Trace tree write failed", exc)
    try:
        traces_repo.save_trace_index(user_id, trace)
    except Exception as exc:  # noqa: BLE001 - never fail a run on the index
        _warn("Trace index write failed", exc)


def local_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


# --- workflow (multi-agent) traces -------------------------------------------
#
# Workflow runs record a different frame shape than single-agent runs
# (`node.started` / `node.stream` / `node.completed` / `node.handoff`), so they
# need their own projection. Without this, workflow runs never reached the trace
# store at all and were missing from the Traces page.


def build_workflow_trace(
    *,
    trace_id: str,
    run_id: str,
    user_id: str,
    workflow_id: str,
    workflow_name: str,
    model: str,
    provider: str | None,
    conversation_id: str | None,
    mode: str,
    question: str,
    answer: str,
    status: str,
    started_at: str,
    ended_at: str,
    events: list[dict[str, Any]],
    usage: dict[str, Any] | None,
    nodes: list[dict[str, Any]] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Project a workflow run's node frames into a trace + observation tree.

    Shape: ``run (SPAN)`` → one ``SPAN`` per agent node (its tool calls nested
    underneath) → the synthesizer/answer ``GENERATION``.
    """
    trace_id = str(trace_id or run_id)
    start_ms = _parse_ms(started_at)
    end_ms = _parse_ms(ended_at)
    latency_ms = (
        max(0, end_ms - start_ms)
        if start_ms is not None and end_ms is not None
        else None
    )

    label_by_node: dict[str, str] = {}
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or node.get("nodeId") or "")
        if node_id:
            label_by_node[node_id] = str(
                node.get("name") or node.get("agentName") or node_id
            )

    observations: list[dict[str, Any]] = []
    root_id = _observation_id(trace_id, "run", "root")
    answer_id = _observation_id(trace_id, "gen", "answer")
    node_spans: dict[str, dict[str, Any]] = {}
    pending_tools: dict[str, dict[str, Any]] = {}
    tool_order: list[str] = []
    error_message: str | None = None
    error_detail: dict[str, Any] = {}
    cursor = start_ms

    def add(observation: dict[str, Any]) -> None:
        if len(observations) < MAX_OBSERVATIONS:
            observations.append(observation)

    def node_span(node_id: str) -> dict[str, Any]:
        span = node_spans.get(node_id)
        if span is None:
            span = {
                "id": _observation_id(trace_id, "node", node_id or "host"),
                "parentObservationId": root_id,
                "type": "SPAN",
                "name": label_by_node.get(node_id) or node_id or "agent",
                "startTime": None,
                "endTime": None,
                "durationMs": None,
                "level": "DEFAULT",
                "input": None,
                "output": None,
                "usage": None,
                "metadata": {"kind": "node", "nodeId": node_id},
            }
            node_spans[node_id] = span
            add(span)
        return span

    def apply_tool_frame(span: dict[str, Any], frame: dict[str, Any], at: int | None) -> None:
        """Fold one agent tool frame into a TOOL observation under ``span``."""
        tool_use_id = str(frame.get("toolUseId") or f"tool-{len(tool_order)}")
        tool = pending_tools.get(tool_use_id)
        if tool is None:
            tool = {
                "id": _observation_id(trace_id, "tool", tool_use_id),
                "parentObservationId": span["id"],
                "type": "TOOL",
                "name": str(frame.get("name") or "tool"),
                "startTime": at,
                "endTime": None,
                "durationMs": None,
                "level": "DEFAULT",
                "input": None,
                "output": None,
                "usage": None,
                "metadata": {},
            }
            pending_tools[tool_use_id] = tool
            tool_order.append(tool_use_id)
        if frame.get("name"):
            tool["name"] = str(frame["name"])
        if frame.get("type") in ("tool.start", "tool.input") and frame.get("input") is not None:
            tool["input"] = _clip(frame.get("input"))
        if frame.get("type") == "tool.result":
            tool["endTime"] = at
            tool["output"] = _clip(frame.get("data"))
            if at is not None and tool.get("startTime") is not None:
                tool["durationMs"] = max(0, at - int(tool["startTime"]))
            tool["level"] = (
                "ERROR" if str(frame.get("status") or "") == "error" else "DEFAULT"
            )
            if frame.get("sources"):
                tool["metadata"]["sources"] = _clip(frame.get("sources"))
            retrieval = _extract_retrieval(frame.get("data"))
            if retrieval:
                tool["metadata"]["retrieval"] = _clip(retrieval)

    for event in events:
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        at = _event_at(event, cursor)
        if at is not None:
            cursor = at

        if kind == "node.started":
            span = node_span(str(event.get("nodeId") or ""))
            span["name"] = str(event.get("agentName") or event.get("nodeName") or span["name"])
            if span.get("startTime") is None:
                span["startTime"] = at
        elif kind == "node.completed":
            span = node_span(str(event.get("nodeId") or ""))
            span["endTime"] = at
            if span.get("startTime") is not None and at is not None:
                span["durationMs"] = max(0, at - int(span["startTime"]))
            span["usage"] = event.get("usage") or None
            if str(event.get("status") or "") == "error":
                span["level"] = "ERROR"
        elif kind == "node.stream":
            node_id = str(event.get("nodeId") or "")
            frame = event.get("event") if isinstance(event.get("event"), dict) else {}
            ftype = frame.get("type")
            if ftype in ("tool.start", "tool.input", "tool.stream", "tool.result"):
                apply_tool_frame(node_span(node_id), frame, at)
            elif ftype == "text":
                span = node_span(node_id)
                if not span.get("output"):
                    span["output"] = _clip(frame.get("data"))
        elif kind == "node.handoff":
            add(
                {
                    "id": _observation_id(trace_id, "event", f"handoff-{len(observations)}"),
                    "parentObservationId": root_id,
                    "type": "EVENT",
                    "name": "handoff",
                    "startTime": at,
                    "endTime": at,
                    "durationMs": 0,
                    "level": "DEFAULT",
                    "input": [str(item) for item in event.get("from") or []],
                    "output": [str(item) for item in event.get("to") or []],
                    "usage": None,
                    "metadata": {"kind": "handoff", "message": _clip(event.get("message"), 4000)},
                }
            )
        elif kind == "question":
            add(
                {
                    "id": _observation_id(trace_id, "event", "question"),
                    "parentObservationId": root_id,
                    "type": "EVENT",
                    "name": "user_question",
                    "startTime": at,
                    "endTime": at,
                    "durationMs": 0,
                    "level": "DEFAULT",
                    "input": _clip(event.get("question")),
                    "output": _clip(event.get("answer")),
                    "usage": None,
                    "metadata": {"options": event.get("options") or []},
                }
            )
        elif kind == "run.error":
            error_message = str(event.get("message") or "workflow run failed")
            for key in ("errorKind", "detail", "stack"):
                if event.get(key):
                    error_detail[key] = str(event.get(key))

    # Close any node span that never reported completion.
    for span in node_spans.values():
        if span.get("startTime") is None:
            span["startTime"] = start_ms
        if span.get("endTime") is None:
            span["endTime"] = end_ms
            if span.get("startTime") is not None and end_ms is not None:
                span["durationMs"] = max(0, end_ms - int(span["startTime"]))

    # Any tool that never returned (errored/aborted run) is an errored span.
    for tool in pending_tools.values():
        if tool["endTime"] is None:
            tool["endTime"] = end_ms
            if tool["startTime"] is not None and end_ms is not None:
                tool["durationMs"] = max(0, end_ms - int(tool["startTime"]))
            tool["level"] = "ERROR"
    for tool_use_id in tool_order:
        add(pending_tools[tool_use_id])

    usage = usage or {}
    add(
        {
            "id": answer_id,
            "parentObservationId": root_id,
            "type": "GENERATION",
            "name": "final answer",
            "model": model or None,
            "startTime": end_ms,
            "endTime": end_ms,
            "durationMs": 0,
            "level": "ERROR" if error_message else "DEFAULT",
            "statusMessage": error_message,
            "input": _clip(question),
            "output": _clip(answer),
            "usage": usage or None,
            "costMicroUsd": _observation_cost(model, usage) if usage else 0,
            "metadata": {"provider": provider, "mode": mode},
        }
    )

    observations.insert(
        0,
        {
            "id": root_id,
            "parentObservationId": None,
            "type": "SPAN",
            "name": workflow_name or workflow_id or "workflow",
            "model": model or None,
            "startTime": start_ms,
            "endTime": end_ms,
            "durationMs": latency_ms,
            "level": "ERROR" if error_message else "DEFAULT",
            "statusMessage": error_message,
            "input": _clip(question),
            "output": _clip(answer),
            "usage": usage or None,
            "costMicroUsd": _observation_cost(model, usage) if usage else 0,
            "metadata": {
                "kind": "run",
                "workflowId": workflow_id,
                "runId": run_id,
                "conversationId": conversation_id,
                "provider": provider,
                "mode": mode,
                "tags": [str(tag) for tag in (tags or [])],
                **({"errorDetail": error_detail} if error_detail else {}),
            },
        },
    )

    type_counts: dict[str, int] = {}
    error_count = 0
    for observation in observations:
        obs_type = str(observation.get("type") or "SPAN")
        type_counts[obs_type] = type_counts.get(obs_type, 0) + 1
        if observation.get("level") == "ERROR":
            error_count += 1

    return {
        "id": trace_id,
        "traceId": trace_id,
        "name": f"workflow:{workflow_name or workflow_id or 'run'}",
        "userId": user_id,
        "sessionId": conversation_id,
        "conversationId": conversation_id,
        "runId": run_id,
        "agentId": workflow_id,
        "agentName": workflow_name,
        "model": model,
        "provider": provider,
        "tags": [str(tag) for tag in (tags or [])],
        "status": _normalize_status(status),
        "level": "ERROR" if error_message else "DEFAULT",
        "statusMessage": error_message,
        "targetType": "workflow",
        "mode": mode,
        "startedAt": started_at,
        "endedAt": ended_at,
        "latencyMs": latency_ms,
        "input": question,
        "output": answer,
        "usage": usage,
        "costMicroUsd": _cost_micro_usd(model, usage),
        "observationCount": len(observations),
        "summary": {
            "observationCount": len(observations),
            "errorCount": error_count,
            "typeCounts": type_counts,
            "totalStageLatencyMs": sum(
                int(o.get("durationMs") or 0)
                for o in observations
                if o.get("id") != root_id
            ),
            "hasSystemPrompt": False,
        },
        "createdAt": started_at,
        "observations": observations,
    }
