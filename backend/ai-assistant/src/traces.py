"""AI Assistant run traces — one observation tree per turn, small index item in DynamoDB.

The tree is the Langfuse-style view the platform already uses for agent runs, and
it is what makes an AI Assistant answer debuggable after the fact: which classifier stage
fired, which passages retrieval returned and with what scores, which tool the
model called, how long each step took, and what it cost.

Only signed-in turns are traced (guest turns are never stored), and each span is
built from the frames the turn already produced — so tracing adds no extra calls
and cannot change the answer.
"""

from __future__ import annotations

import time
from typing import Any

from data.repositories import ai_assistant as ai_assistant_repo

from src import metrics
from src.conversations import summarise_frames
from src.identity import Identity

MAX_SPANS = 40


def build_tree(
    *,
    question: str,
    frames: list[dict[str, Any]],
    intent: dict[str, Any] | None,
    model: str,
    entry_route: str = "",
    surface: str = "user",
    error: str = "",
) -> dict[str, Any]:
    """Build the observation tree for one AI Assistant turn."""
    summary = summarise_frames(frames)
    spans: list[dict[str, Any]] = []

    if intent:
        spans.append(
            {
                "name": "ai-assistant.classifier",
                "kind": "classifier",
                "stage": intent.get("stage"),
                "verdict": intent.get("kind"),
                "intent": intent.get("intent"),
                "confidence": intent.get("confidence"),
                "examples": len(intent.get("examples") or []),
            }
        )

    for frame in frames:
        kind = frame.get("type")
        if kind == "tool.result":
            entry: dict[str, Any] = {
                "name": str(frame.get("name") or "tool"),
                "kind": "tool",
                "toolUseId": frame.get("toolUseId"),
                "ms": None,
                "sources": len(frame.get("sources") or []),
            }
            result = frame.get("data")
            if isinstance(result, (str, dict, list)):
                entry["resultPreview"] = str(result)[:400]
            spans.append(entry)
        elif kind == "text":
            # One span per contiguous narration run would be noise; summarise.
            continue

    completed = next(
        (frame for frame in frames if frame.get("type") == "run.completed"), None
    )
    usage = summary.get("usage") or {}
    cost = metrics.cost_micro_usd(
        model, int(usage.get("inputTokens") or 0), int(usage.get("outputTokens") or 0)
    )

    return {
        "traceId": "",
        "name": "ai-assistant.turn",
        "surface": surface,
        "entryRoute": entry_route,
        "question": question[:1_000],
        "answer": summary["answer"][:4_000],
        "output": {"text": summary["answer"], "sources": summary["sources"]},
        "model": model,
        "usage": usage,
        "costMicroUsd": cost,
        "latencyMs": summary.get("latencyMs"),
        "ttftMs": summary.get("ttftMs"),
        "stopReason": summary.get("stopReason") or "",
        "status": "error" if (error or summary.get("error")) else "ok",
        "error": (error or summary.get("error") or "")[:500],
        "classifier": intent or {},
        "spans": spans[:MAX_SPANS],
        "completedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "finished": bool(completed),
    }


def record_trace(
    request: Any,
    frames: list[dict[str, Any]],
    *,
    identity: Identity | None = None,
    intent: dict[str, Any] | None = None,
    error: str = "",
    entry_route: str = "",
) -> dict[str, Any] | None:
    """Persist one AI Assistant trace (tree in S3, small index item in DynamoDB)."""
    if identity is None or identity.is_guest:
        return None

    question = str(getattr(request, "question", "") or "")
    model = str(getattr(request, "model", "") or "")
    surface = str(getattr(request, "surface", "user") or "user")
    conversation_id = str(getattr(request, "conversation_id", "") or "")
    run_id = str(getattr(request, "run_id", "") or "")

    tree = build_tree(
        question=question,
        frames=frames,
        intent=intent,
        model=model,
        entry_route=entry_route,
        surface=surface,
        error=error,
    )
    summary = summarise_frames(frames)
    usage = summary.get("usage") or {}
    trace_id = run_id or ai_assistant_repo.new_run_id()
    tree["traceId"] = trace_id

    item = ai_assistant_repo.put_trace(
        identity.user_id,
        trace_id,
        tree=tree,
        summary={
            "question": question,
            "answerPreview": summary["answer"][:400],
            "model": model,
            "classifierKind": (intent or {}).get("kind"),
            "intent": (intent or {}).get("intent"),
            "status": tree["status"],
            "latencyMs": summary.get("latencyMs"),
            "ttftMs": summary.get("ttftMs"),
            "tokensIn": int(usage.get("inputTokens") or 0),
            "tokensOut": int(usage.get("outputTokens") or 0),
            "costMicroUsd": tree["costMicroUsd"],
            "sourceCount": len(summary["sources"]),
            "spanCount": len(tree["spans"]),
            "conversationId": conversation_id,
            "runId": run_id,
            "entryRoute": entry_route,
            "stopReason": summary.get("stopReason"),
        },
    )
    return item


def list_traces(
    user_id: str, *, limit: int = 50
) -> tuple[list[dict[str, Any]], str | None]:
    items, cursor = ai_assistant_repo.list_traces(user_id, limit=limit)
    return items, ai_assistant_repo.encode_cursor(cursor)


def get_trace(user_id: str, trace_id: str) -> dict[str, Any] | None:
    return ai_assistant_repo.get_trace(user_id, trace_id)
