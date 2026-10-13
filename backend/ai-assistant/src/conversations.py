"""Persist an AI Assistant turn (signed-in callers only).

The browser always sends the whole conversation, so this transcript is **not** the
source of truth for a turn — it exists for replay, admin review and evaluation,
and it is written **after** the answer has streamed. Both properties matter: a
storage failure must never cost the user an answer, and a guest turn is never
written at all (that is what makes the guest path stateless).

One S3 object per conversation (the bulky transcript) plus one small DynamoDB
item (metadata, counts, preview) — the same shape the platform's chat uses.
"""

from __future__ import annotations

import time
from typing import Any

from data.repositories import ai_assistant as ai_assistant_repo

from src.identity import Identity

#: Answer characters kept in the metadata preview and trace index.
PREVIEW_CHARS = 400


def summarise_frames(frames: list[dict[str, Any]]) -> dict[str, Any]:
    """Pull the answer, usage, timings and sources out of a finished run."""
    answer = ""
    usage: dict[str, Any] = {}
    latency_ms: int | None = None
    ttft_ms: int | None = None
    sources: list[dict[str, Any]] = []
    tool_calls: list[str] = []
    error = ""
    stop_reason = ""

    for frame in frames:
        kind = frame.get("type")
        if kind == "run.completed":
            answer = str(frame.get("text") or "")
            usage = frame.get("usage") or {}
            latency_ms = frame.get("latencyMs")
            ttft_ms = frame.get("ttftMs")
            stop_reason = str(frame.get("stopReason") or "")
            for source in frame.get("sources") or []:
                if isinstance(source, dict):
                    sources.append(source)
        elif kind == "tool.result":
            tool_calls.append(str(frame.get("name") or ""))
            for source in frame.get("sources") or []:
                if isinstance(source, dict):
                    sources.append(source)
        elif kind == "run.error":
            error = str(frame.get("message") or "")

    # De-duplicate sources by route/title so a re-query does not repeat them.
    seen: set[tuple[str, str]] = set()
    unique_sources: list[dict[str, Any]] = []
    for source in sources:
        key = (str(source.get("route") or ""), str(source.get("title") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique_sources.append(source)
        if len(unique_sources) >= 12:
            break

    return {
        "answer": answer,
        "usage": usage,
        "latencyMs": latency_ms,
        "ttftMs": ttft_ms,
        "sources": unique_sources,
        "toolCalls": tool_calls,
        "error": error,
        "stopReason": stop_reason,
    }


def build_turn(
    *,
    question: str,
    summary: dict[str, Any],
    intent: dict[str, Any] | None,
    model: str,
    entry_route: str = "",
) -> dict[str, Any]:
    """The turn record written to the transcript (and reused by the trace)."""
    turn: dict[str, Any] = {
        "question": question,
        "answer": summary["answer"],
        "model": model,
        "entryRoute": entry_route,
        "sources": summary["sources"],
        "toolCalls": summary["toolCalls"],
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if summary.get("latencyMs") is not None:
        turn["latencyMs"] = summary["latencyMs"]
    if summary.get("ttftMs") is not None:
        turn["ttftMs"] = summary["ttftMs"]
    usage = summary.get("usage") or {}
    if usage:
        turn["tokensIn"] = int(usage.get("inputTokens") or 0)
        turn["tokensOut"] = int(usage.get("outputTokens") or 0)
    if intent:
        turn["classifierKind"] = intent.get("kind")
        turn["intent"] = intent.get("intent")
        turn["classifierStage"] = intent.get("stage")
    if summary.get("error"):
        turn["error"] = summary["error"]
    if summary.get("stopReason"):
        turn["stopReason"] = summary["stopReason"]
    return turn


def record_turn(
    request: Any,
    frames: list[dict[str, Any]],
    identity: Identity | None = None,
    *,
    intent: dict[str, Any] | None = None,
    error: str = "",
) -> dict[str, Any] | None:
    """Append the finished turn to the caller's conversation.

    Returns ``None`` when there is nothing to store (a guest, or no conversation
    id — the caller may be evaluating rather than chatting).
    """
    if identity is None or identity.is_guest:
        return None
    conversation_id = str(getattr(request, "conversation_id", "") or "")
    if not conversation_id:
        return None

    summary = summarise_frames(frames)
    if error and not summary.get("error"):
        summary["error"] = error

    turn = build_turn(
        question=str(getattr(request, "question", "") or ""),
        summary=summary,
        intent=intent,
        model=str(getattr(request, "model", "") or ""),
        entry_route=str(getattr(request, "route", "") or ""),
    )

    ai_assistant_repo.append_turn(identity.user_id, conversation_id, turn)
    return turn


def ensure_conversation(identity: Identity, *, entry_route: str = "", model: str = "") -> str:
    """Create a conversation up front so a turn always has somewhere to land."""
    item = ai_assistant_repo.create_conversation(
        identity.user_id, entry_route=entry_route, model=model
    )
    return str(item["conversationId"])
