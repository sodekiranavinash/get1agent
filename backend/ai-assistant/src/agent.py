"""Assemble and run AI Assistant's LangChain Deep Agents turn.

AI Assistant is the platform's one **non-Strands** agent. It uses the Deep Agents harness
for what that harness is genuinely good at — a plan, context management, and a
bounded loop — while deliberately declining the parts a support widget must not
have (see ``_permissions`` and the absent subagents).

Two paths, chosen from the classifier verdict, because they have very different
cost profiles:

* **Answer path** — a tool-using agent turn for platform questions. It calls
  :func:`~ai-assistant.tools.search_platform_docs`, which retrieves before the first model
  call, so prompt-injected text can neither steer retrieval nor see the docs.
* **Direct path** — one model call, no tools, for a greeting or an off-topic
  nudge. Paying for a deep-agent graph to say "I'm here for the platform" would be
  absurd.

The whole turn is an async generator of the platform's SSE frames
(:mod:`ai-assistant.frames`), so the FastAPI service, the MicroVM proxy and the guest
Lambda all consume the same thing.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from src import deep_links, metrics, prompts, retrieval, settings
from src.classifier import Verdict, fail_open
from src.frames import (
    STAGE_COMPOSE,
    STAGE_INTENT,
    STAGE_KNOWLEDGE,
    STAGE_LINKS,
    STAGE_PLAN,
    STAGE_TOOL,
    FrameWriter,
    flatten_content,
    usage_from_message,
)

# NOTE: langchain/langgraph are imported **inside** the functions that need them,
# never at module import. That keeps this module (and therefore the shared
# package) importable by the guest Lambda, whose zip and cold start must not carry
# a 150 MB agent framework it will never use.

#: Nodes that can carry a model's answer. Deep Agents uses ``model`` for its main
#: agent and ``tools`` for tool execution; anything else is middleware.
_MODEL_NODES = ("model",)
_TOOL_NODES = ("tools",)


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class TurnRequest:
    """Everything one AI Assistant turn needs — nothing is read from globals or the DB."""

    question: str
    history: list[dict[str, str]] = field(default_factory=list)
    route: str = ""
    conversation_id: str = ""
    run_id: str = ""
    user_id: str = ""
    is_guest: bool = False
    #: The admin page's AI Assistant may also explain the admin console and link to it.
    allow_admin: bool = False
    #: Overrides for evaluation runs and the admin playground.
    model: str = ""
    answer_mode: str = "summarize"
    retrieve: bool = True
    use_agent: bool = True
    #: Where this turn is being measured from: ``guest`` | ``user`` | ``eval``.
    surface: str = "user"

    @property
    def effective_surface(self) -> str:
        if self.surface in ("guest", "user", "eval"):
            return self.surface
        return "guest" if self.is_guest else "user"


def _history_messages(history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Convert the browser's transcript into LangChain chat messages.

    The browser sends the whole conversation every turn (AI Assistant keeps no server-side
    turn state), so this is the only source of continuity. The window is bounded
    because a widget conversation can grow without limit.
    """
    if not history:
        return []
    max_turns = settings.max_history_turns()
    max_chars = settings.max_history_chars()

    cleaned: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        cleaned.append({"role": role, "content": content})

    # Keep the most recent turns, then trim from the front until it fits.
    cleaned = cleaned[-(max_turns * 2) :]
    while cleaned and sum(len(item["content"]) for item in cleaned) > max_chars:
        cleaned.pop(0)
    return cleaned


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #


def _make_tools(state: "_RunState") -> list[Any]:
    """The agent's tools: retrieval, deep links, support — and nothing else.

    Retrieval happens **before** the first model call (``state.passages`` is
    already populated), so this tool is the model asking for a second look with a
    sharper query. That ordering is deliberate: untrusted text never gets to
    choose what is retrieved.
    """
    from langchain_core.tools import tool  # noqa: PLC0415 - keeps import cost off the rules path

    @tool
    def search_platform_docs(query: str) -> str:
        """Search the get1agent platform documentation for an answer.

        Use it when the passages already provided do not cover the question, or to
        narrow a broad question. Returns matching documentation sections with the
        page route to link.
        """
        passages, diagnostic = retrieval.search(
            query,
            top_k=4,
            audience="admin" if state.allow_admin else "user",
            allow_admin=state.allow_admin,
        )
        state.diagnostics.append(diagnostic)
        state.retrieval_calls += 1
        state.passages.extend(passages)
        if not passages:
            return "No documentation matched that query."
        return json.dumps(
            [
                {
                    "title": passage.title,
                    "route": passage.route,
                    "content": (passage.matched or passage.content)[:1200],
                }
                for passage in passages
            ],
            ensure_ascii=False,
        )

    @tool
    def find_page(feature: str) -> str:
        """Find the product page for a feature the user is asking about.

        Use it to answer "where do I do X". Returns the page name and the exact
        route to link. Only routes returned here may be linked.
        """
        found = deep_links.find(feature, allow_admin=state.allow_admin)
        if not found:
            return "No page matched that feature name."
        state.linked_routes.append(found.path)
        return json.dumps(
            {"name": found.label, "route": found.path, "note": found.note},
            ensure_ascii=False,
        )

    @tool
    def escalate_to_support(reason: str) -> str:
        """Tell the user how to reach a human when AI Assistant cannot help.

        Use it when the question is about their specific account, a bug, billing
        they dispute, or anything the documentation does not cover.
        """
        return (
            "Point the user to the Support page (`/support`), where they can message "
            "the team directly. Mention that a security issue has its own form on "
            f"the same page. Reason recorded: {reason[:200]}"
        )

    tools: list[Any] = [search_platform_docs, find_page, escalate_to_support]
    return tools


# --------------------------------------------------------------------------- #
# Run state
# --------------------------------------------------------------------------- #


@dataclass
class _RunState:
    request: TurnRequest
    allow_admin: bool = False
    passages: list[retrieval.Passage] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    linked_routes: list[str] = field(default_factory=list)
    retrieval_calls: int = 0
    model_calls: int = 0
    #: Set once a tool has returned, so the harness knows the model is answering.
    tool_results_seen: bool = False
    #: True while a tool call is being assembled (the text so far is preamble).
    tool_call_in_flight: bool = False
    #: The last non-empty assistant message, used when nothing streamed.
    final_text: str = ""
    cap_hit: bool = False


def _model(model_id: str) -> Any:
    """Build the streaming Bedrock chat model.

    ``disable_streaming=False`` is not optional: ``ChatBedrockConverse`` silently
    disables streaming for providers it does not recognise as streaming-capable
    (``zai``, ``qwen``), and the turn would then arrive as one blob at the end.
    """
    from langchain_aws import ChatBedrockConverse  # noqa: PLC0415 - heavy, only needed per run

    return ChatBedrockConverse(
        model=model_id,
        region_name=settings.region(),
        disable_streaming=False,
        temperature=float(os.environ.get("AI_ASSISTANT_TEMPERATURE", "0.2") or "0.2"),
        max_tokens=int(os.environ.get("AI_ASSISTANT_MAX_TOKENS", "1200") or "1200"),
    )


def _turn_cap_class() -> type:
    """Build the step-cap middleware class.

    Subclassing the harness's own ``AgentMiddleware`` (rather than duck-typing a
    plain class) matters: the middleware base carries a ``name`` and the hook
    registry the graph assembles against, so a bare class fails at graph build
    time rather than at request time.
    """
    from langchain.agents.middleware import AgentMiddleware  # noqa: PLC0415

    class TurnCap(AgentMiddleware):
        """Stop a runaway agent loop.

        A support widget must answer quickly and cheaply, and the failure mode of a
        tool-using agent is an unbounded loop. Capping the model calls per turn
        bounds cost by construction rather than by hope.
        """

        def __init__(self, max_steps: int) -> None:
            super().__init__()
            self.max_steps = max(1, max_steps)
            self.calls = 0

        def wrap_model_call(self, request: Any, handler: Any) -> Any:
            self.calls += 1
            if self.calls > self.max_steps:
                raise TurnCapExceeded(
                    f"AI Assistant stopped after {self.max_steps} steps to keep the answer quick."
                )
            return handler(request)

        async def awrap_model_call(self, request: Any, handler: Any) -> Any:
            self.calls += 1
            if self.calls > self.max_steps:
                raise TurnCapExceeded(
                    f"AI Assistant stopped after {self.max_steps} steps to keep the answer quick."
                )
            return await handler(request)

    return TurnCap


class TurnCapExceeded(RuntimeError):
    """Raised when one AI Assistant turn exceeds its model-call budget."""


def _build_agent(model_id: str, system_prompt: str, state: _RunState) -> tuple[Any, Any]:
    """Assemble the deep agent: tools, a step cap, and read-only permissions."""
    from deepagents import create_deep_agent  # noqa: PLC0415
    from deepagents.backends import StateBackend  # noqa: PLC0415

    cap = _turn_cap_class()(settings.max_agent_steps())

    # AI Assistant is read-only: its scratch filesystem lives in graph state, there is no
    # shell, and there are no subagents — delegation would multiply the loops the
    # step cap exists to prevent.
    permissions: list[Any] = []
    if _env_flag("AI_ASSISTANT_DENY_FILESYSTEM_WRITES", True):
        try:
            from deepagents.middleware.filesystem import FilesystemPermission  # noqa: PLC0415

            permissions = [FilesystemPermission(operations=["read"])]
        except Exception:  # noqa: BLE001 - a harness change must not break AI Assistant
            permissions = []

    agent = create_deep_agent(
        model=_model(model_id),
        system_prompt=system_prompt,
        tools=_make_tools(state),
        middleware=[cap],
        permissions=permissions,
        subagents=[],
        backend=StateBackend(),
    )
    return agent, cap


# --------------------------------------------------------------------------- #
# Direct answer (greeting / nudge / retrieval failure)
# --------------------------------------------------------------------------- #


async def _stream_direct(
    writer: FrameWriter,
    model_id: str,
    system_prompt: str,
    user_text: str,
    *,
    note: str = "",
) -> AsyncIterator[dict[str, Any]]:
    """Stream one model call with no tools (a greeting, or the off-topic nudge)."""
    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

    model = _model(model_id)
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_text)]
    async for chunk in model.astream(messages):
        delta = flatten_content(getattr(chunk, "content", ""))
        if delta:
            frame = writer.text_delta(delta)
            if frame:
                compose = writer.composing("Writing your answer")
                if compose:
                    yield compose
                yield frame
        usage = usage_from_message(chunk)
        if usage.input_tokens or usage.output_tokens:
            writer.usage.input_tokens = max(writer.usage.input_tokens, usage.input_tokens)
            writer.usage.output_tokens = max(writer.usage.output_tokens, usage.output_tokens)


# --------------------------------------------------------------------------- #
# The turn
# --------------------------------------------------------------------------- #


async def run_turn(
    request: TurnRequest,
    *,
    verdict: Verdict | None = None,
    classifier: Any = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run one AI Assistant turn, yielding normalized SSE frames.

    The sequence is: ``run.started`` → ``ai-assistant.intent`` → (plan) → text/tool frames →
    ``run.completed``. A failure anywhere becomes ``run.error`` with the partial
    answer preserved, so the widget can show what it has.
    """
    started = time.perf_counter()
    model_id = request.model or settings.model()
    writer = FrameWriter(
        run_id=request.run_id or f"avirun_{int(time.time() * 1000)}",
        model=model_id,
        conversation_id=request.conversation_id,
        entry_route=request.route,
        is_guest=request.is_guest,
    )
    state = _RunState(request=request)

    yield writer.run_started()

    # --- 1. Classify ------------------------------------------------------
    # Announced before the work, not after: the classifier is a real model call on
    # a cold path, so this is the stage the user actually waits through first.
    yield writer.stage(STAGE_INTENT, "Working out what you're asking")
    classifier_started = time.perf_counter()
    if verdict is None:
        from src.classifier import Classifier  # noqa: PLC0415

        classifier = classifier or Classifier(model_id=settings.classifier_model())
        verdict = await asyncio.to_thread(
            classifier.classify, request.question, route=request.route
        )
    intent_frame = verdict.to_frame()
    yield intent_frame
    classifier_ms = int((time.perf_counter() - classifier_started) * 1000)

    # --- 2. Off-topic / greeting: one cheap model call, no retrieval ------
    if not verdict.is_platform:
        metrics.turn(
            surface=request.effective_surface,
            model=model_id,
            intent_kind=verdict.kind,
            intent_stage=verdict.stage,
            latency_ms=writer.latency_ms,
            ttft_ms=None,
            tokens_in=0,
            tokens_out=0,
            source_count=0,
            tool_calls=0,
            refused=True,
            classifier_latency_ms=classifier_ms,
        )
        async for frame in _stream_direct(
            writer,
            model_id,
            prompts.off_topic_prompt(
                request.question, request.route, verdict.examples
            ),
            request.question,
        ):
            yield frame
        yield writer.completed(stop_reason="off_topic")
        return

    # A greeting needs no retrieval and no agent graph: one cheap model call, the
    # same path the guest Lambda takes. The condition used to also require
    # `not request.retrieve`, which no caller ever sets — so "hi" ran hybrid search
    # and a full tool loop, and the live log said "Searching the platform docs" for
    # hello. Greetings are the most common first message, so this is also the
    # cheapest latency and cost win in the turn.
    if verdict.is_smalltalk:
        async for frame in _stream_direct(
            writer, model_id, prompts.greeting_prompt(request.route), request.question
        ):
            yield frame
        yield writer.completed(stop_reason="smalltalk")
        return

    # --- 3. Retrieve before the first model call --------------------------
    state.allow_admin = request.allow_admin
    #: The audience travels with every retrieval call, not just the tool's. It is
    #: part of the search cache key (`retrieval._cache_key`), so an admin's
    #: passage list — which legitimately includes admin docs — must never be
    #: stored under the key a signed-in user's identical question would read.
    audience = "admin" if state.allow_admin else "user"
    if request.retrieve:
        # Announced *before* the await: hybrid search is the slowest silent part of
        # a turn (embed + two legs + fusion), and it is exactly what the user is
        # staring at when nothing has been said yet.
        yield writer.stage(STAGE_KNOWLEDGE, "Searching the platform docs")
        passages, diagnostic = await asyncio.to_thread(
            retrieval.search,
            request.question,
            top_k=6,
            audience=audience,
            allow_admin=state.allow_admin,
        )
        state.passages = passages
        state.diagnostics.append(diagnostic)
        metrics.retrieval(diagnostic, surface=request.effective_surface)
        # Register the up-front passages as sources BEFORE the model answers, so the
        # inline `[n]` citations it writes resolve to a real card. Waiting for a
        # tool call would leave `[1]` pointing at nothing, because retrieval has
        # already happened and the model has no reason to call the search tool.
        for passage in passages:
            source = passage.to_source()
            # Never register an admin route as a citation for a non-admin turn,
            # whatever the corpus says about the document's audience.
            if not state.allow_admin and not deep_links.is_valid(
                str(source.get("route") or ""), allow_admin=False
            ):
                source["route"] = ""
                source["url"] = "/docs"
            source["index"] = len(writer.sources) + 1
            writer.sources.append(source)

        if passages:
            yield writer.stage(
                STAGE_LINKS,
                "Choosing the pages to cite",
                detail=f"{len(passages)} matched",
            )

    # --- 4. Answer --------------------------------------------------------
    system_prompt = prompts.build_system_prompt(
        passages=retrieval.as_prompt_passages(state.passages),
        answer_mode=request.answer_mode,
        route=request.route,
        is_guest=request.is_guest,
        allow_admin=state.allow_admin,
    )

    if not request.use_agent or not _env_flag("AI_ASSISTANT_AGENT_ENABLED", True):
        async for frame in _stream_direct(writer, model_id, system_prompt, request.question):
            yield frame
        _emit_turn_metrics(writer, verdict, request, classifier_ms)
        yield writer.completed()
        return

    yield writer.stage(STAGE_PLAN, "Planning how to answer")
    for frame in writer.plan(
        [
            {
                "id": "q1",
                "query": request.question[:200],
                "todos": [
                    {
                        "id": "t1",
                        "title": "Search the platform documentation",
                        "tool": "search_platform_docs",
                        "query": request.question[:200],
                    }
                ],
            }
        ]
    ):
        yield frame

    try:
        agent, cap = _build_agent(model_id, system_prompt, state)
    except Exception as exc:  # noqa: BLE001 - never fail the turn on setup
        yield writer.failed(f"Agent unavailable: {type(exc).__name__}: {exc}", retryable=True)
        _emit_turn_metrics(writer, verdict, request, classifier_ms, failed=True)
        return

    messages = [*_history_messages(request.history), {"role": "user", "content": request.question}]
    tool_names: dict[str, str] = {}

    try:
        async for mode, chunk in agent.astream(
            {"messages": messages}, stream_mode=["messages", "updates"]
        ):
            if mode == "messages":
                for frame in _frames_from_message_chunk(writer, chunk, tool_names):
                    yield frame
            else:
                for frame in _frames_from_update(writer, chunk, tool_names, state):
                    yield frame
    except Exception as exc:  # noqa: BLE001 - surface a usable error frame
        # Log the real reason. Without this a failed turn is indistinguishable from
        # a model that refused to answer, which makes local debugging guesswork.
        print(
            json.dumps(
                {
                    "level": "error",
                    "message": "ai-assistant turn failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "retrievalCalls": state.retrieval_calls,
                    "modelCalls": cap.calls,
                }
            ),
            file=sys.stderr,
            flush=True,
        )
        traceback.print_exc()
        state.cap_hit = cap.calls > cap.max_steps
        # A cap breach and a provider error read very differently to a user.
        message = (
            "That question needed more digging than I can do in one go. "
            "Try asking something more specific."
            if state.cap_hit
            else "I hit a problem answering that. Please try again in a moment."
        )
        yield writer.failed(message, retryable=True)
        _emit_turn_metrics(writer, verdict, request, classifier_ms, failed=True)
        return

    # The streamed text is the answer; if the model said nothing (a pure tool
    # turn), fall back to the last non-empty assistant message.
    if not writer.answer.strip():
        fallback = _last_assistant_text(getattr(state, "final_text", ""))
        if fallback:
            frame = writer.text_delta(fallback)
            if frame:
                compose = writer.composing()
                if compose:
                    yield compose
                yield frame

    _emit_turn_metrics(writer, verdict, request, classifier_ms)
    yield writer.completed()


def _last_assistant_text(value: str) -> str:
    return value.strip()


def _emit_turn_metrics(
    writer: FrameWriter,
    verdict: Verdict,
    request: TurnRequest,
    classifier_ms: int,
    *,
    failed: bool = False,
) -> None:
    metrics.turn(
        surface=request.effective_surface,
        model=writer.model,
        intent_kind=verdict.kind,
        intent_stage=verdict.stage,
        latency_ms=writer.latency_ms,
        ttft_ms=writer.ttft_ms,
        tokens_in=writer.usage.input_tokens,
        tokens_out=writer.usage.output_tokens,
        source_count=len(writer.sources),
        tool_calls=len(writer.tool_calls),
        refused=False,
        failed=failed,
        classifier_latency_ms=classifier_ms,
    )


def _frames_from_message_chunk(
    writer: FrameWriter,
    chunk: Any,
    tool_names: dict[str, str],
) -> list[dict[str, Any]]:
    """Turn one ``messages`` stream chunk into frames."""
    frames: list[dict[str, Any]] = []
    message, _meta = chunk if isinstance(chunk, tuple) else (chunk, {})
    if message is None:
        return frames

    for tool_chunk in getattr(message, "tool_call_chunks", None) or []:
        chunk_id = tool_chunk.get("id")
        name = tool_chunk.get("name")
        if chunk_id and name:
            tool_names[chunk_id] = str(name)
            frame = writer.tool_start(str(chunk_id), str(name))
            if frame:
                frames.append(frame)
                # The tool's real work is about to start; say what it is, in words,
                # with the tool's actual name kept alongside it.
                frames.append(
                    writer.stage(
                        STAGE_TOOL,
                        _tool_label(str(name)),
                        detail=_tool_detail(tool_chunk.get("args")),
                        tool=str(name),
                    )
                )
        elif name and not chunk_id:
            # Continuation of the same tool call: find the open one.
            open_ids = [key for key in writer.started_tools if key not in _closed_ids(writer)]
            target = open_ids[-1] if open_ids else ""
            if target:
                frame = writer.tool_input(target, tool_chunk.get("args") or "")
                if frame:
                    frames.append(frame)
        args = tool_chunk.get("args")
        if chunk_id and args:
            frame = writer.tool_input(str(chunk_id), args)
            if frame:
                frames.append(frame)

    delta = flatten_content(getattr(message, "content", ""))
    if delta:
        frame = writer.text_delta(delta)
        if frame:
            compose = writer.composing()
            if compose:
                frames.append(compose)
            frames.append(frame)

    usage = usage_from_message(message)
    if usage.input_tokens or usage.output_tokens:
        writer.usage.input_tokens = max(writer.usage.input_tokens, usage.input_tokens)
        writer.usage.output_tokens = max(writer.usage.output_tokens, usage.output_tokens)

    return frames


def _closed_ids(writer: FrameWriter) -> set[str]:
    return {str(call.get("id") or "") for call in writer.tool_calls}


#: What each tool is *for*, in AI Assistant's own voice. The live log is only honest if the
#: label describes the job rather than repeating the function name at the user.
_TOOL_LABELS: dict[str, str] = {
    "search_platform_docs": "Searching the docs again, with a sharper query",
    "find_page": "Locating the page you need",
    "escalate_to_support": "Finding the right way to reach a human",
}


def _tool_label(name: str) -> str:
    return _TOOL_LABELS.get(name, f"Checking with {name}")


def _tool_detail(raw_args: Any) -> str:
    """The literal argument behind a tool stage, so the log stays checkable.

    Tool arguments stream in as a partial JSON string, so this is best-effort: a
    half-written value is worse than none.
    """
    if not isinstance(raw_args, str) or not raw_args.strip():
        return ""
    try:
        parsed = json.loads(raw_args)
    except (ValueError, TypeError):
        return ""
    if isinstance(parsed, dict):
        for key in ("query", "feature", "reason"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:120]
    return ""


def _frames_from_update(
    writer: FrameWriter,
    chunk: Any,
    tool_names: dict[str, str],
    state: _RunState,
) -> list[dict[str, Any]]:
    """Turn one ``updates`` stream chunk into frames (tool results + usage)."""
    frames: list[dict[str, Any]] = []
    if not isinstance(chunk, dict):
        return frames

    for node, update in chunk.items():
        if not isinstance(update, dict):
            continue
        messages = update.get("messages") or []
        if not isinstance(messages, (list, tuple)):
            continue

        if node in _TOOL_NODES:
            for message in messages:
                tool_call_id = str(getattr(message, "tool_call_id", "") or "")
                name = tool_names.get(tool_call_id) or str(
                    getattr(message, "name", "") or "tool"
                )
                content = getattr(message, "content", "")
                payload: Any = content
                if isinstance(content, str):
                    try:
                        payload = json.loads(content)
                    except (ValueError, TypeError):
                        payload = content
                sources = _sources_from_payload(payload, writer, allow_admin=state.allow_admin)
                frames.append(
                    writer.tool_result(tool_call_id, name, payload, sources=sources or None)
                )
                state.tool_results_seen = True

        if node in _MODEL_NODES:
            for message in messages:
                usage = usage_from_message(message)
                if usage.input_tokens or usage.output_tokens:
                    # LangChain reports cumulative usage per node, not per chunk.
                    writer.usage.input_tokens = max(
                        writer.usage.input_tokens, usage.input_tokens
                    )
                    writer.usage.output_tokens = max(
                        writer.usage.output_tokens, usage.output_tokens
                    )
                text = flatten_content(getattr(message, "content", ""))
                if getattr(message, "tool_calls", None):
                    state.tool_call_in_flight = True
                elif text.strip():
                    state.tool_call_in_flight = False
                    state.final_text = text

    return frames


def _sources_from_payload(
    payload: Any, writer: FrameWriter, *, allow_admin: bool = False
) -> list[dict[str, Any]]:
    """Extract the citations a tool returned, numbered run-globally.

    The numbering matches the inline ``[n]`` markers the system prompt asks for,
    so the UI's source carousel and the answer agree.

    ``allow_admin`` gates the route, not just the retrieval: a tool payload is
    model-shaped data, so accepting an admin path here because "retrieval already
    filtered" would hand a normal user a link into the console the moment any
    payload carried one.
    """
    if not isinstance(payload, list):
        return []
    sources: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        route = str(item.get("route") or "")
        if route and not deep_links.is_valid(route, allow_admin=allow_admin):
            route = ""
        index = len(writer.sources) + len(sources) + 1
        sources.append(
            {
                "kind": "knowledge",
                "index": index,
                "title": str(item.get("title") or "Platform docs"),
                "subtitle": route or "Platform documentation",
                "route": route,
                "url": route or "/docs",
                "snippet": str(item.get("content") or "")[:600],
            }
        )
    return sources


def classify_only(question: str, *, route: str = "") -> Verdict:
    """Classify without running a turn (the admin page and evaluations use this)."""
    from src.classifier import Classifier  # noqa: PLC0415

    try:
        return Classifier(model_id=settings.classifier_model()).classify(
            question, route=route
        )
    except Exception as exc:  # noqa: BLE001
        return fail_open(f"{type(exc).__name__}: {exc}")
