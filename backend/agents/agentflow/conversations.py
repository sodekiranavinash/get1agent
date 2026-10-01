"""Persist chat/builder conversation transcripts (S3) + metadata (DynamoDB).

The bulky transcript — every turn with its full run events — lives in one S3
object per conversation (``retrieval.layout.conversation_key``). The small
metadata item (counts, recency, preview) is updated in DynamoDB so the sidebar
and the builder history never touch S3. Both writes are best-effort: a storage
failure must never fail the run.
"""

from __future__ import annotations

import json
from typing import Any

from agentflow.config import RuntimeConfig
from core.storage import Storage
from data.client import now_iso
from data.repositories import conversations as conversations_repo
from retrieval.layout import conversation_key


def _warn(message: str, exc: BaseException) -> None:
    print(
        json.dumps({"level": "warning", "message": message, "error": str(exc)}),
        flush=True,
    )


def append_turn(
    config: RuntimeConfig,
    user_id: str,
    conversation_id: str | int,
    turn: dict[str, Any],
    *,
    replace_run_id: str | None = None,
) -> None:
    """Read-modify-write the conversation transcript (one object per chat).

    ``replace_run_id`` rewrites that run's existing turn in place instead of
    appending — how a human-in-the-loop resume replaces the paused turn.
    """
    if not config.s3_bucket:
        return
    storage = Storage()
    key = conversation_key(user_id, conversation_id)
    data = storage.get_json(key) or {}
    turns = data.get("turns")
    if not isinstance(turns, list):
        turns = []
    replaced = False
    if replace_run_id:
        for index, existing in enumerate(turns):
            if isinstance(existing, dict) and str(existing.get("runId") or "") == str(
                replace_run_id
            ):
                turns[index] = turn
                replaced = True
                break
    if not replaced:
        turns.append(turn)
    storage.put_json(
        key,
        {
            "conversationId": int(conversation_id),
            "userId": user_id,
            "turns": turns,
            "updatedAt": now_iso(),
        },
    )


def persist_turn(
    config: RuntimeConfig,
    user_id: str,
    conversation_id: str | int,
    turn: dict[str, Any],
    *,
    run_id: str,
    preview: str = "",
    trace_id: str | None = None,
    trace_url: str | None = None,
    replace_run_id: str | None = None,
) -> None:
    # Only persist for a conversation that actually exists. A stale/unknown id
    # (e.g. a deleted conversation still in a tab's URL) must not write an
    # orphan transcript: conversation ids come from one global counter, so a
    # later conversation could be assigned the same id and appear to inherit
    # the orphan turns.
    try:
        conversation_number = int(conversation_id)
    except (TypeError, ValueError) as exc:
        _warn("Conversation id is not numeric; skipping persistence", exc)
        return
    try:
        if conversations_repo.get_conversation(user_id, conversation_number) is None:
            _warn(
                "Skipping persistence for unknown conversation",
                KeyError(str(conversation_id)),
            )
            return
    except Exception as exc:  # noqa: BLE001 - never fail a run on the check
        _warn("Conversation lookup failed; skipping persistence", exc)
        return

    try:
        append_turn(
            config,
            user_id,
            conversation_number,
            turn,
            replace_run_id=replace_run_id,
        )
    except Exception as exc:  # noqa: BLE001 - never fail a run on persistence
        _warn("Conversation transcript write failed", exc)
    try:
        conversations_repo.record_run(
            user_id,
            conversation_number,
            run_id=run_id,
            preview=preview,
            trace_id=trace_id,
            trace_url=trace_url,
        )
    except Exception as exc:  # noqa: BLE001
        _warn("Conversation metadata update failed", exc)
