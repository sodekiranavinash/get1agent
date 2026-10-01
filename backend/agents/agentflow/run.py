"""Run one agent: load its config, build the Strands agent, stream events."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, AsyncIterator

from agentflow.attachments import build_attachment_block, resolve_file_ids
from agentflow.config import load_config
from agentflow.context import TruncatingModel
from agentflow.conversations import persist_turn
from agentflow.events import normalize_many
from agentflow.hitl import (
    ASK_USER_TOOL,
    build_ask_user_tool,
    interrupt_responses,
    pending_interrupt_responses,
    question_from_interrupt,
    tool_use_id_from_interrupt_id,
)
from agentflow.identity import resolve_user_id
from agentflow.memory import DynamoMemoryStore
from agentflow.models import (
    DEFAULT_CONTEXT_WINDOW,
    build_model,
    context_window_limit,
    resolve_model_id,
)
from agentflow.observability import flush, run_trace, trace_identity
from agentflow.planner import build_plan, execution_input
from agentflow.provider import record_provider_usage, resolve_model_provider
from agentflow.prompts import build_system_prompt
from agentflow.sessions import build_session_manager
from agentflow.store import load_agent, resolve_knowledge_bases, resolve_skills
from agentflow.tools import build_tools
from data.client import now_iso
from data.repositories import quotas

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


def _answer_text(recorded: list[dict[str, Any]]) -> str:
    """The run's final answer text (the last streamed text frame)."""
    for event in reversed(recorded):
        if event.get("type") == "text" and event.get("data"):
            return str(event["data"]).strip()
    return ""


def _answer_preview(recorded: list[dict[str, Any]]) -> str:
    return _answer_text(recorded)[:280]


def _trace_tags(
    agent_name: str,
    model: str,
    agent_config: dict[str, Any],
    provider_name: str = "",
) -> list[str]:
    """Langfuse tags: agent, model and the knowledge/MCP surfaces in play."""
    tags = ["agent"]
    if agent_name:
        tags.append(agent_name)
    if model:
        tags.append(model)
    if provider_name:
        tags.append(f"provider:{provider_name}")
    if agent_config.get("knowledgeBaseIds"):
        tags.append("knowledge")
    return tags


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
    provider: dict[str, Any] | None = None
    provider_secret_id = ""
    run_usage: dict[str, Any] = {}
    platform_run = True
    budget_ok = True
    original_input = ""
    started_at = now_iso()
    recorded: list[dict[str, Any]] = []
    status = "completed"
    # Human-in-the-loop (chat only): `human_in_loop` is None when the caller
    # never opted in, True to let the agent ask, False to make it assume.
    raw_hitl = payload.get("humanInLoop")
    human_in_loop: bool | None = raw_hitl if isinstance(raw_hitl, bool) else None
    resume_responses = interrupt_responses(payload)
    resume_run_id = str(payload.get("resumeRunId") or "").strip() or None
    pending_question = payload.get("pendingQuestion")
    pending_question = pending_question if isinstance(pending_question, dict) else None
    awaiting_input = False
    # `ask_user` tool calls are represented by the question card, never as a tool
    # row in the timeline.
    hidden_tool_ids: set[str] = set()
    context_state: dict[str, Any] | None = None
    trace = None
    observation: Any = None
    trace_id: str | None = None
    trace_url: str | None = None

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
        if not user_input and not resume_responses:
            raise ValueError("input is required")
        # On resume the client re-sends the original question for the transcript,
        # and the pending question so a replayed turn still shows the ask card.
        if resume_responses and pending_question:
            question_id = str(pending_question.get("questionId") or "")
            hidden_tool_ids.add(tool_use_id_from_interrupt_id(question_id))
            recorded.append({"type": "question", **pending_question})

        # A caller (e.g. the chat screen) may override the agent's saved model
        # for a single run; otherwise fall back to the agent's config.
        requested_model = str(payload.get("model") or "").strip() or agent_config.get("model")

        # The agent may run on one of the user's Vault provider secrets instead
        # of the platform gateway. Resolve it before building the model; a
        # missing/broken provider fails the run rather than silently billing the
        # platform key.
        # Presence-based: an explicit empty string in the payload means "run on
        # the platform gateway", overriding a provider saved on the agent.
        if "providerSecretId" in payload:
            provider_secret_id = str(payload.get("providerSecretId") or "").strip()
        else:
            provider_secret_id = str(agent_config.get("providerSecretId") or "").strip()
        if provider_secret_id:
            provider = resolve_model_provider(user_id, provider_secret_id)
            resolved_model = (
                str(requested_model or "").strip()
                or str((provider or {}).get("defaultModel") or "").strip()
            )
            if not resolved_model:
                raise ValueError("Select a model for the chosen provider")
        else:
            resolved_model = resolve_model_id(requested_model)

        # Budget gate. Runs on the platform gateway are refused once the user's
        # application budget is spent; a run on the user's own provider key is
        # always allowed, but planning (which uses the platform key) is skipped
        # for an over-budget user so the app spends nothing on them.
        platform_run = provider is None
        try:
            budget = quotas.get_budget(user_id)
            budget_ok = budget.unlimited or not budget.exceeded
        except Exception:  # noqa: BLE001 - a budget read must never break a run
            budget_ok = True
        if platform_run and not budget_ok:
            raise RuntimeError(
                "Your AI credits are used up. Add your own API key in the Vault "
                "to keep running, or ask an admin for more credits."
            )

        # Per-run answer-mode / reasoning overrides from the chat composer.
        requested_mode = str(payload.get("answerMode") or "").strip()
        if requested_mode:
            agent_config = {**agent_config, "answerMode": requested_mode}
        requested_reasoning = str(payload.get("reasoning") or "").strip()
        if requested_reasoning:
            agent_config = {**agent_config, "reasoning": requested_reasoning}

        # Per-run resource overrides from the chat run-config dialog. An empty list
        # is meaningful ("none selected"), so only a list is accepted.
        for key in ("skillIds", "knowledgeBaseIds"):
            override = payload.get(key)
            if isinstance(override, list):
                agent_config = {
                    **agent_config,
                    key: [str(value) for value in override if str(value or "").strip()],
                }
        override_servers = payload.get("servers")
        if isinstance(override_servers, list) and all(
            isinstance(entry, dict) for entry in override_servers
        ):
            agent_config = {**agent_config, "servers": override_servers}

        file_ids = resolve_file_ids(payload, agent_config)

        yield {
            "type": "run.started",
            "runId": run_id,
            "agentId": agent_id,
            "sessionId": conversation_id,
            "model": resolved_model,
            # Present only when the run is on the user's own Vault provider.
            "provider": (provider or {}).get("name"),
        }

        # One Langfuse trace per run: the planner, every model turn and every
        # tool call nest under it. A no-op unless Langfuse credentials are set.
        trace = run_trace(
            f"agent:{agent_name or agent_id}",
            input=user_input,
            user_id=user_id,
            session_id=conversation_id,
            tags=_trace_tags(
                agent_name,
                resolved_model,
                agent_config,
                str((provider or {}).get("name") or ""),
            ),
            metadata={
                "agentId": agent_id,
                "agentName": agent_name,
                "runId": run_id,
                "conversationId": conversation_id,
                "providerSecretId": provider_secret_id or None,
            },
        )
        observation = trace.__enter__()

        knowledge = resolve_knowledge_bases(
            user_id, list(agent_config.get("knowledgeBaseIds") or [])
        )
        skills = resolve_skills(user_id, list(agent_config.get("skillIds") or []))
        # Tell the client which skills are available to the agent. Skills are
        # injected by the AgentSkills plugin via progressive disclosure (metadata
        # only) and activated on demand through the `skills` tool, so this frame is
        # what lets the run card show the skill set that was loaded.
        if skills:
            skills_event = {
                "type": "skills",
                "skills": [
                    {"id": skill.get("id"), "name": skill.get("name")}
                    for skill in skills
                    if skill.get("name")
                ],
            }
            _record(recorded, skills_event)
            yield skills_event

        from agentflow.skills import build_skills_plugin
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

        # Bound tool output sent to the model (the session keeps the full data).
        model = TruncatingModel(
            build_model(config, resolved_model, conversation_id, provider=provider)
        )
        tools = build_tools(
            config,
            user_id,
            agent_config,
            [kb["name"] for kb in knowledge],
        )
        # Chat-only: let the agent pause and ask the user when uncertain. On a
        # resume the tool must be present again so the paused call can replay,
        # even if auto-approve was turned on after the question was asked.
        if human_in_loop or resume_responses:
            tools.append(build_ask_user_tool())
        system_prompt = build_system_prompt(
            agent_config, skills, human_in_loop=human_in_loop
        )
        # Progressive disclosure: the plugin injects skill metadata into the system
        # prompt and exposes the `skills` activation tool. The agent decides which
        # skill (if any) applies.
        skills_plugin = build_skills_plugin(skills)

        # Construct the agent first: this restores the conversation history from
        # the S3 session, so both the planner and the context meter see it. The
        # summarizing manager compacts only when the next call would overflow, so
        # the run that crosses the limit still completes instead of erroring.
        agent_runtime = Agent(
            name=agent_name or agent_id,
            model=model,
            tools=tools,
            plugins=[skills_plugin] if skills_plugin else None,
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
        planner_input = user_input
        if file_ids:
            planner_input = (
                f"{user_input}\n\n(Note: {len(file_ids)} attached file(s) come with "
                "this run — their text is provided automatically, no tool call is "
                "needed to read them.)"
            )
        plan = None
        if config.planner_enabled and budget_ok and not resume_responses:
            try:
                yield {"type": "plan.started"}
                _record(recorded, {"type": "plan.started"})
                plan = build_plan(
                    config,
                    agent_config,
                    planner_input,
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

        if resume_responses:
            # The user answered the pending question: Strands replays the paused
            # tool call with these responses and the agent continues.
            execution: Any = resume_responses
        else:
            execution = user_input
            if plan:
                plan_event = {"type": "plan", **plan}
                _record(recorded, plan_event)
                yield plan_event
                execution = execution_input(user_input, plan)

            # Download the attached storage files at invocation time (never pre-baked
            # into the prompt) and fold their extracted text into the model input.
            if file_ids:
                attachment_block, attachments = build_attachment_block(user_id, file_ids)
                if attachments:
                    attachments_event = {"type": "attachments", "files": attachments}
                    _record(recorded, attachments_event)
                    yield attachments_event
                if attachment_block:
                    execution = f"{execution}\n\n{attachment_block}"

        # A session can still be paused at a question when a new message arrives
        # (e.g. a stale tab). Resume the pending interrupt with the message folded
        # in rather than failing with "must resume from interrupt ...".
        if not resume_responses and isinstance(execution, str):
            recovered = pending_interrupt_responses(agent_runtime, execution)
            if recovered:
                resume_responses = recovered
                execution = recovered

        seen_tool_uses: set[str] = set()
        last_inputs: dict[str, Any] = {}

        async for event in agent_runtime.stream_async(execution):
            # Human-in-the-loop: the run paused for the user's answer. Surface the
            # question and stop (no run.completed) so the client can resume it.
            raw_result = event.get("result") if isinstance(event, dict) else None
            if raw_result is not None and str(
                getattr(raw_result, "stop_reason", "") or ""
            ) == "interrupt":
                for interrupt in getattr(raw_result, "interrupts", None) or []:
                    question = question_from_interrupt(interrupt)
                    if not question:
                        continue
                    hidden_tool_ids.add(
                        tool_use_id_from_interrupt_id(str(question.get("questionId") or ""))
                    )
                    frame = {"type": "question", **question}
                    _record(recorded, frame)
                    yield frame
                awaiting_input = True
                status = "awaiting_input"
                continue

            for normalized in normalize_many(event):
                # The `ask_user` call is rendered as the question card, not a tool
                # row in the run timeline.
                if (
                    normalized.get("type") == "tool.start"
                    and normalized.get("name") == ASK_USER_TOOL
                ):
                    tool_use_id = str(normalized.get("toolUseId") or "")
                    if tool_use_id:
                        hidden_tool_ids.add(tool_use_id)
                    continue
                if normalized.get("type") in ("tool.input", "tool.stream", "tool.result"):
                    if str(normalized.get("toolUseId") or "") in hidden_tool_ids:
                        continue
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
                elif normalized.get("type") == "run.completed":
                    run_usage = normalized.get("usage") or {}
                _record(recorded, normalized)
                yield normalized

        # Capture the trace id + public URL (marking the trace public) while the
        # root observation is still recording, then tell the client about it so
        # the chat can link the message to its trace.
        if observation is not None:
            try:
                trace_id, trace_url = trace_identity(observation)
            except Exception:  # noqa: BLE001 - tracing must never break a run
                pass
        if trace_id or trace_url:
            trace_event = {"type": "trace", "traceId": trace_id, "traceUrl": trace_url}
            _record(recorded, trace_event)
            yield trace_event

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

        if observation is not None:
            observation.update(output=_answer_text(recorded))

    except Exception as exc:  # noqa: BLE001 - surface any failure to the client
        status = "error"
        failure = {"type": "run.error", "message": str(exc)}
        recorded.append(failure)
        if observation is not None:
            try:
                observation.update(level="ERROR", status_message=str(exc))
            except Exception:  # noqa: BLE001 - tracing must never break a run
                pass
        yield failure
    finally:
        if trace is not None:
            # Fallback capture if the body didn't reach the trace step (e.g. an
            # error before the stream finished), then close the root observation.
            if trace_id is None and trace_url is None:
                try:
                    trace_id, trace_url = trace_identity(observation)
                except Exception:  # noqa: BLE001 - tracing must never break a run
                    pass
            try:
                trace.__exit__(None, None, None)
            except Exception:  # noqa: BLE001 - tracing must never break a run
                pass
        # Persist the turn so the conversation can be reopened (and continued)
        # later. Best-effort: persistence never changes the run's outcome.
        try:
            # A paused run is persisted too (so the question survives a reload);
            # the resume replaces that same turn via `replace_run_id`.
            if (
                config is not None
                and user_id
                and agent_id
                and conversation_id is not None
            ):
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
                        "traceId": trace_id,
                        "traceUrl": trace_url,
                        "context": context_state,
                        "events": recorded,
                    },
                    run_id=run_id,
                    preview=_answer_preview(recorded),
                    trace_id=trace_id,
                    trace_url=trace_url,
                    replace_run_id=resume_run_id,
                )
        except Exception:  # noqa: BLE001 - persistence never changes the outcome
            pass
        # Attribute the run's tokens to the Vault provider secret that paid for
        # them. Recorded here (not after the stream loop) so a partial/errored
        # run still counts; only when the provider resolved (a resolution failure
        # before any model call must not count) and never on the platform path.
        if provider is not None and provider_secret_id and user_id:
            record_provider_usage(user_id, provider_secret_id, run_usage, resolved_model)
        elif platform_run and user_id:
            # Charge the platform-gateway run to the user's application budget.
            try:
                quotas.charge_usage(
                    user_id,
                    model=resolved_model,
                    input_tokens=run_usage.get("inputTokens") or 0,
                    output_tokens=run_usage.get("outputTokens") or 0,
                )
            except Exception:  # noqa: BLE001 - accounting never breaks a run
                pass
        # The container can suspend between invocations, so flush buffered spans.
        # Always runs (even if the client disconnected and the run was cancelled).
        flush()
