"""Run one agent: load its config, build the Strands agent, stream events."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, AsyncIterator

from agentflow.config import load_config
from agentflow.context import TruncatingModel
from agentflow.conversations import persist_turn
from agentflow.events import normalize_many
from agentflow.identity import resolve_user_id
from agentflow.memory import DynamoMemoryStore
from agentflow.models import (
    DEFAULT_CONTEXT_WINDOW,
    build_model,
    context_window_limit,
    resolve_model_id,
)
from agentflow.planner import build_plan, execution_input
from agentflow.prompts import build_system_prompt
from agentflow.sessions import build_session_manager
from agentflow.store import load_agent, resolve_knowledge_bases, resolve_skills
from agentflow.tools import build_tools
from data.client import now_iso

# Summarize the oldest turns once the context is this full, so the run that
# crosses the limit still completes instead of erroring.
COMPRESSION_THRESHOLD = float(os.environ.get("AGENT_CONTEXT_COMPRESSION_THRESHOLD", "0.9"))
# After a run, a conversation at/over this fill is "full": the UI tells the user
# to start a new conversation and stops accepting messages.
FULL_RATIO = float(os.environ.get("AGENT_CONTEXT_FULL_RATIO", "0.9"))
# How many prior turns the planner sees (bounded so planning stays cheap).
PLANNER_HISTORY_TURNS = int(os.environ.get("AGENT_PLANNER_HISTORY_TURNS", "6"))


def _conversation_id(payload: dict[str, Any], context: Any) -> str:
    for key in ("conversationId", "sessionId"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return str(getattr(context, "session_id", "") or "default")


def _input_text(payload: dict[str, Any], agent_config: dict[str, Any]) -> str:
    text = payload.get("input")
    if text is None:
        text = payload.get("prompt")
    if text is None:
        text = (agent_config.get("input") or {}).get("query")
    return str(text or "").strip()


def _record(recorded: list[dict[str, Any]], event: dict[str, Any]) -> None:
    """Accumulate the run's frames, coalescing streamed text deltas."""
    if event.get("type") == "text":
        text = str(event.get("data") or "")
        if recorded and recorded[-1].get("type") == "text":
            recorded[-1]["data"] = str(recorded[-1].get("data") or "") + text
        else:
            recorded.append({"type": "text", "data": text})
        return
    recorded.append(event)


def _answer_preview(recorded: list[dict[str, Any]]) -> str:
    for event in reversed(recorded):
        if event.get("type") == "text" and event.get("data"):
            return str(event["data"]).strip()[:280]
    return ""


def _history_messages(messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Text-only user/assistant turns (the planner can't consume tool blocks)."""
    history: list[dict[str, Any]] = []
    for message in messages or []:
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        text = "".join(
            str(block.get("text") or "")
            for block in (message.get("content") or [])
            if isinstance(block, dict) and block.get("text")
        ).strip()
        if text:
            history.append({"role": role, "content": [{"text": text}]})
    return history


async def _count(
    model: Any,
    messages: list[dict[str, Any]],
    *,
    tool_specs: list[dict[str, Any]] | None = None,
    system_prompt: str | None = None,
) -> int:
    try:
        return int(
            await model.count_tokens(
                messages, tool_specs=tool_specs, system_prompt=system_prompt
            )
        )
    except Exception:  # noqa: BLE001 - a meter must never break a run
        return 0


async def _context_frame(
    model: Any,
    messages: list[dict[str, Any]],
    tool_specs: list[dict[str, Any]],
    system_prompt: str,
    limit: int,
    full: bool,
) -> dict[str, Any]:
    """Context fill + a per-component token breakdown (system/tools/messages)."""
    system_tokens = await _count(model, [], system_prompt=system_prompt)
    tool_tokens = await _count(model, [], tool_specs=tool_specs)
    message_tokens = await _count(model, messages)
    used = system_tokens + tool_tokens + message_tokens
    ratio = (used / limit) if limit else 0.0
    return {
        "type": "context",
        "usedTokens": used,
        "limitTokens": limit,
        "ratio": round(ratio, 4),
        "full": full,
        "breakdown": {
            "system": system_tokens,
            "tools": tool_tokens,
            "messages": message_tokens,
        },
    }


async def run_agent_stream(payload: Any, context: Any) -> AsyncIterator[dict[str, Any]]:
    payload = payload if isinstance(payload, dict) else {}
    run_id = uuid.uuid4().hex

    config = None
    user_id: str | None = None
    agent_id = ""
    agent_name = ""
    conversation_id: str | None = None
    resolved_model = ""
    original_input = ""
    started_at = now_iso()
    recorded: list[dict[str, Any]] = []
    status = "completed"
    context_state: dict[str, Any] | None = None

    try:
        config = load_config()
        user_id = resolve_user_id(payload, context)
        agent_id = str(payload.get("agentId") or "").strip()
        if not agent_id:
            raise ValueError("agentId is required")

        agent = load_agent(user_id, agent_id)
        agent_config = agent.get("config") or {}
        agent_name = str(agent.get("name") or "")
        conversation_id = _conversation_id(payload, context)
        user_input = _input_text(payload, agent_config)
        original_input = user_input
        if not user_input:
            raise ValueError("input is required")

        yield {
            "type": "run.started",
            "runId": run_id,
            "agentId": agent_id,
            "sessionId": conversation_id,
        }

        knowledge = resolve_knowledge_bases(
            user_id, list(agent_config.get("knowledgeBaseIds") or [])
        )
        skills = resolve_skills(user_id, list(agent_config.get("skillIds") or []))

        from strands import Agent
        from strands.agent.conversation_manager import SummarizingConversationManager
        from strands.memory import MemoryManager

        memory_enabled = bool((agent_config.get("memory") or {}).get("enabled"))
        memory_manager = None
        if memory_enabled:
            memory_manager = MemoryManager(
                stores=[DynamoMemoryStore(user_id, agent_id)],
                add_tool_config=True,
            )

        # A caller (e.g. the chat screen) may override the agent's saved model
        # for a single run; otherwise fall back to the agent's config.
        requested_model = str(payload.get("model") or "").strip() or agent_config.get("model")
        resolved_model = resolve_model_id(requested_model)
        # Bound tool output sent to the model (the session keeps the full data).
        model = TruncatingModel(build_model(config, resolved_model, conversation_id))
        tools = build_tools(
            config,
            user_id,
            agent_config,
            [kb["name"] for kb in knowledge],
        )
        system_prompt = build_system_prompt(agent_config, skills)

        # Construct the agent first: this restores the conversation history from
        # the S3 session, so both the planner and the context meter see it. The
        # summarizing manager compacts only when the next call would overflow, so
        # the run that crosses the limit still completes instead of erroring.
        agent_runtime = Agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            session_manager=build_session_manager(
                config, user_id, agent_id, conversation_id
            ),
            memory_manager=memory_manager,
            conversation_manager=SummarizingConversationManager(
                preserve_recent_messages=10,
                proactive_compression={"compression_threshold": COMPRESSION_THRESHOLD},
            ),
            callback_handler=None,
        )

        limit = int(model.context_window_limit or DEFAULT_CONTEXT_WINDOW)
        tool_specs = agent_runtime.tool_registry.get_all_tool_specs()
        pre_frame = await _context_frame(
            model, agent_runtime.messages, tool_specs, system_prompt, limit, False
        )
        pre_used = pre_frame["usedTokens"]
        pre_frame["full"] = pre_used / limit >= FULL_RATIO if limit else False
        yield pre_frame

        # Plan first: derive the sub-queries and an ordered todo list, stream the
        # plan to the client so it can render a live checklist, then fold it into
        # the agent's instructions so the run follows it. A planner failure is
        # non-fatal — the run proceeds unplanned.
        plan = None
        if config.planner_enabled:
            try:
                yield {"type": "plan.started"}
                _record(recorded, {"type": "plan.started"})
                plan = build_plan(
                    config,
                    agent_config,
                    user_input,
                    [getattr(tool, "tool_name", "") for tool in tools],
                    [kb["name"] for kb in knowledge],
                    skills,
                    conversation_id,
                    _history_messages(agent_runtime.messages)[
                        -(2 * PLANNER_HISTORY_TURNS) :
                    ],
                )
            except Exception as exc:  # noqa: BLE001 - planning must never block a run
                print(
                    json.dumps(
                        {
                            "level": "warning",
                            "message": "Planning step failed; running without a plan",
                            "error": str(exc),
                        }
                    ),
                    flush=True,
                )
                plan = None

        if plan:
            plan_event = {"type": "plan", **plan}
            _record(recorded, plan_event)
            yield plan_event
            user_input = execution_input(user_input, plan)

        seen_tool_uses: set[str] = set()
        last_inputs: dict[str, Any] = {}

        async for event in agent_runtime.stream_async(user_input):
            for normalized in normalize_many(event):
                # The model streams a tool's input incrementally, so
                # ``current_tool_use`` fires many times per call. Emit
                # ``tool.start`` once per toolUseId, then forward each later
                # snapshot as ``tool.input`` so the UI can render the invocation
                # as it is being built.
                if normalized.get("type") == "tool.start":
                    tool_use_id = str(normalized.get("toolUseId") or "")
                    if tool_use_id and tool_use_id in seen_tool_uses:
                        current_input = normalized.get("input")
                        if current_input == last_inputs.get(tool_use_id):
                            continue
                        last_inputs[tool_use_id] = current_input
                        normalized = {
                            "type": "tool.input",
                            "toolUseId": tool_use_id,
                            "input": current_input,
                        }
                    elif tool_use_id:
                        seen_tool_uses.add(tool_use_id)
                        last_inputs[tool_use_id] = normalized.get("input")
                elif normalized.get("type") == "tool.result":
                    # Carry the fully-built arguments on the result frame too, so
                    # a client that missed the stream still sees the invocation.
                    tool_use_id = str(normalized.get("toolUseId") or "")
                    recorded_input = last_inputs.get(tool_use_id)
                    if recorded_input is not None and not normalized.get("input"):
                        normalized["input"] = recorded_input
                _record(recorded, normalized)
                yield normalized

        # Recompute after the turn: mark the conversation full once it crosses the
        # threshold so the UI can ask the user to start a new one.
        post_frame = await _context_frame(
            model, agent_runtime.messages, tool_specs, system_prompt, limit, False
        )
        post_used = post_frame["usedTokens"]
        post_frame["full"] = (
            max(pre_used, post_used) / limit >= FULL_RATIO if limit else False
        )
        context_state = post_frame
        _record(recorded, context_state)
        yield context_state

    except Exception as exc:  # noqa: BLE001 - surface any failure to the client
        status = "error"
        failure = {"type": "run.error", "message": str(exc)}
        recorded.append(failure)
        yield failure
    finally:
        # Persist the turn so the conversation can be reopened (and continued)
        # later. Best-effort: persistence never changes the run's outcome.
        if config is not None and user_id and agent_id and conversation_id is not None:
            persist_turn(
                config,
                user_id,
                conversation_id,
                {
                    "runId": run_id,
                    "question": original_input,
                    "model": resolved_model,
                    "agentId": agent_id,
                    "agentName": agent_name,
                    "startedAt": started_at,
                    "completedAt": now_iso(),
                    "status": status,
                    "context": context_state,
                    "events": recorded,
                },
                run_id=run_id,
                preview=_answer_preview(recorded),
            )
