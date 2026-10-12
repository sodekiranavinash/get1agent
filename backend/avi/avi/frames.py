"""Translate Avi's run into the platform's existing SSE frame contract.

The frontend already knows how to render a streamed run: ``lib/runState.ts``
reduces ``run.started | plan.started | plan | text | tool.start | tool.input |
tool.result | run.completed | run.error`` and ``components/chat`` renders it. Avi
emits **the same frames**, so the widget needs no answer renderer of its own — and
the only new frame is ``avi.intent``, which existing reducers ignore.

This module is deliberately dependency-free (no LangChain import) so it can be
unit-tested and reused by both the MicroVM service and the guest Lambda.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

#: Avi's own frame — the classifier verdict, emitted before any text.
FRAME_INTENT = "avi.intent"

#: Avi's live-progress frame: what the turn is doing *right now*.
#:
#: Deliberately emitted by the backend rather than inferred by the widget. Avi is
#: the only component that knows that retrieval has started, that a tool call is
#: assembling arguments, or that the model has begun to write — guessing from
#: timer ticks produces the "Reading the platform docs…" for 9 seconds that says
#: nothing. Stages are appended in order, so the client keeps a live log without
#: needing a state machine or a "done" round trip.
FRAME_STAGE = "avi.stage"

#: Stage keys, in the order a normal question moves through them.
STAGE_INTENT = "intent"
STAGE_KNOWLEDGE = "knowledge"
STAGE_LINKS = "links"
STAGE_PLAN = "plan"
STAGE_TOOL = "tool"
STAGE_COMPOSE = "compose"


def sse(event: dict[str, Any]) -> str:
    """Serialise one frame as a Server-Sent Event."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def flatten_content(content: Any) -> str:
    """Flatten a model chunk's content into plain text.

    LangChain returns either a string or a list of typed blocks
    (``[{"type": "text", "text": "…"}]``), and Bedrock streams the latter — the
    single most common source of "the answer is blank" in a new streaming agent.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        block_type = str(content.get("type") or "")
        if block_type in ("text", "text_delta", ""):
            return str(content.get("text") or content.get("content") or "")
        return ""
    if isinstance(content, (list, tuple)):
        return "".join(flatten_content(item) for item in content)
    return str(content)


@dataclass
class Usage:
    """Token accounting for one run (reported to the client and the trace)."""

    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, int]:
        return {
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "totalTokens": self.total,
        }


def usage_from_message(message: Any) -> Usage:
    """Read token usage off a LangChain message's ``usage_metadata``."""
    meta = getattr(message, "usage_metadata", None)
    if not isinstance(meta, dict):
        return Usage()
    return Usage(
        input_tokens=int(meta.get("input_tokens") or 0),
        output_tokens=int(meta.get("output_tokens") or 0),
    )


def extract_text_from_state(values: Any) -> str:
    """The final assistant text from a graph state (fallback when not streamed)."""
    if isinstance(values, dict):
        messages = values.get("messages")
    else:
        messages = getattr(values, "messages", None)
    if not isinstance(messages, (list, tuple)):
        return ""
    for message in reversed(messages):
        role = getattr(message, "type", "") or getattr(message, "role", "")
        if role in ("ai", "assistant"):
            text = flatten_content(getattr(message, "content", ""))
            if text.strip():
                return text
    return ""


@dataclass
class FrameWriter:
    """Builds the normalized frames for one Avi run.

    Stateful because a run must emit ``run.started`` exactly once, ``tool.start``
    once per tool-use id (the model streams a tool's arguments incrementally), and
    a terminal frame exactly once.
    """

    run_id: str
    model: str
    conversation_id: str = ""
    entry_route: str = ""
    is_guest: bool = False

    started_at: float = field(default_factory=time.perf_counter)
    first_token_at: float | None = None
    text: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    started_tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    usage: Usage = field(default_factory=Usage)
    _started: bool = False
    _terminal: bool = False
    _composing: bool = False

    # --- timings ---------------------------------------------------------
    @property
    def ttft_ms(self) -> int | None:
        if self.first_token_at is None:
            return None
        return int((self.first_token_at - self.started_at) * 1000)

    @property
    def latency_ms(self) -> int:
        return int((time.perf_counter() - self.started_at) * 1000)

    @property
    def answer(self) -> str:
        return "".join(self.text)

    # --- frames ----------------------------------------------------------
    def run_started(self) -> dict[str, Any]:
        self._started = True
        frame: dict[str, Any] = {
            "type": "run.started",
            "runId": self.run_id,
            "agentId": "avi",
            "sessionId": self.conversation_id or self.run_id,
            "model": self.model,
        }
        if self.entry_route:
            frame["entryRoute"] = self.entry_route
        if self.is_guest:
            frame["guest"] = True
        return frame

    def text_delta(self, delta: str) -> dict[str, Any] | None:
        """One answer chunk, in the platform's ``text`` frame shape.

        The field is ``data`` — that is what ``lib/runState.ts`` appends to
        ``answer``. Emitting ``text`` here makes the widget concatenate
        ``undefined`` once per chunk, so this key is part of the contract, not a
        naming preference.
        """
        if not delta:
            return None
        if self.first_token_at is None:
            self.first_token_at = time.perf_counter()
        self.text.append(delta)
        return {"type": "text", "data": delta}

    def note(self, message: str) -> dict[str, Any]:
        """Narration shown while Avi works (never part of the answer).

        Carries its own frame type so the shared reducer ignores it: a ``text``
        frame with no ``data`` would render as a literal "undefined".
        """
        return {"type": "avi.note", "text": message}

    def stage(
        self,
        key: str,
        label: str,
        *,
        detail: str = "",
        tool: str = "",
    ) -> dict[str, Any]:
        """One live-progress step, appended to the widget's work log.

        ``label`` is the human sentence ("Searching the platform docs"), and the
        optional ``detail``/``tool`` carry the literal thing behind it — the real
        tool name, the classified intent, a count. Keeping both is what makes the
        log honest rather than decorative.
        """
        frame: dict[str, Any] = {"type": FRAME_STAGE, "stage": key, "label": label}
        if detail:
            frame["detail"] = detail
        if tool:
            frame["tool"] = tool
        return frame

    def composing(self, label: str = "Writing your answer") -> dict[str, Any] | None:
        """The 'assembling the answer' stage, emitted once — on the first chunk.

        One-shot because the model streams hundreds of chunks: a stage per chunk
        would be a log of noise, and emitting it up front would claim the answer is
        being written while the model is still deciding.
        """
        if self._composing:
            return None
        self._composing = True
        return self.stage(STAGE_COMPOSE, label)

    def tool_start(self, tool_use_id: str, name: str) -> dict[str, Any] | None:
        """Emit once per tool-use id, with argument snapshots after that.

        Text streamed **before** a tool call is preamble ("let me check the
        docs"), never the answer, so the accumulator is reset here — exactly as
        ``runState.applyToolStart`` resets the client's. Without this the two
        disagree: the client blanks its answer on the tool call and the final
        ``run.completed.text`` would carry preamble glued to the real answer.
        """
        if not tool_use_id or tool_use_id in self.started_tools:
            return None
        self.text.clear()
        record = {"id": tool_use_id, "name": name, "input": "", "startedAt": time.perf_counter()}
        self.started_tools[tool_use_id] = record
        return {
            "type": "tool.start",
            "toolUseId": tool_use_id,
            "name": name,
            "server": "avi",
        }

    def tool_input(self, tool_use_id: str, arguments: Any) -> dict[str, Any] | None:
        record = self.started_tools.get(tool_use_id)
        if record is None:
            return None
        snapshot = (
            arguments
            if isinstance(arguments, str)
            else json.dumps(arguments, ensure_ascii=False, default=str)
        )
        record["input"] = snapshot
        return {
            "type": "tool.input",
            "toolUseId": tool_use_id,
            "input": snapshot,
        }

    def tool_result(
        self,
        tool_use_id: str,
        name: str,
        result: Any,
        *,
        sources: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        record = self.started_tools.get(tool_use_id) or {}
        entry: dict[str, Any] = {
            "id": tool_use_id,
            "name": name,
            "input": record.get("input") or "",
            "result": result,
            "ms": int((time.perf_counter() - record.get("startedAt", self.started_at)) * 1000)
            if record
            else None,
        }
        if sources:
            entry["sources"] = sources
            self.sources.extend(sources)
        self.tool_calls.append(entry)
        # The wire frame carries ``data`` — always a string, because ``runState``
        # renders it as tool output — plus the ``status`` the reducer reads.
        data = (
            result
            if isinstance(result, str)
            else json.dumps(result, ensure_ascii=False, default=str)
        )
        frame: dict[str, Any] = {
            "type": "tool.result",
            "toolUseId": tool_use_id,
            "name": name,
            "status": "success",
            "data": data,
        }
        if sources:
            frame["sources"] = sources
        return frame

    def plan(self, sub_queries: list[dict[str, Any]], understanding: str = "") -> list[dict[str, Any]]:
        """A minimal plan frame so the run card has something to show."""
        frames = [{"type": "plan.started"}]
        frames.append(
            {
                "type": "plan",
                "understanding": understanding or "Answering your question about the platform.",
                "subQueries": sub_queries,
            }
        )
        return frames

    def completed(self, stop_reason: str = "end_turn") -> dict[str, Any]:
        self._terminal = True
        return {
            "type": "run.completed",
            "runId": self.run_id,
            "text": self.answer,
            "usage": self.usage.to_dict(),
            "sources": self.sources,
            "latencyMs": self.latency_ms,
            "ttftMs": self.ttft_ms,
            "stopReason": stop_reason,
            "model": self.model,
        }

    def failed(self, message: str, *, retryable: bool = False) -> dict[str, Any]:
        self._terminal = True
        return {
            "type": "run.error",
            "runId": self.run_id,
            "message": message[:500],
            "retryable": retryable,
            "latencyMs": self.latency_ms,
        }

    def summary(self, intent: dict[str, Any] | None = None) -> dict[str, Any]:
        """The persisted turn / trace summary for this run."""
        payload: dict[str, Any] = {
            "runId": self.run_id,
            "model": self.model,
            "answer": self.answer,
            **self.usage.to_dict(),
            "latencyMs": self.latency_ms,
            "ttftMs": self.ttft_ms,
            "sourceCount": len(self.sources),
            "spanCount": len(self.tool_calls) + 2,
            "status": "ok" if self._terminal else "incomplete",
        }
        if self.conversation_id:
            payload["conversationId"] = self.conversation_id
        if intent:
            payload["classifierKind"] = intent.get("kind")
            payload["intent"] = intent.get("intent")
        return payload


def collect_text(chunks: Iterable[Any]) -> str:
    """Flatten an iterable of content payloads (helper for tests and adapters)."""
    return "".join(flatten_content(chunk) for chunk in chunks)
