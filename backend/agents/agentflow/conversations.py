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
) -> None:
    """Read-modify-write the conversation transcript (one object per chat)."""
    if not config.s3_bucket:
        return
    storage = Storage()
    key = conversation_key(user_id, conversation_id)
    data = storage.get_json(key) or {}
    turns = data.get("turns")
    if not isinstance(turns, list):
        turns = []
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
) -> None:
    try:
        append_turn(config, user_id, conversation_id, turn)
    except Exception as exc:  # noqa: BLE001 - never fail a run on persistence
        _warn("Conversation transcript write failed", exc)
    try:
        conversations_repo.record_run(
            user_id, int(conversation_id), run_id=run_id, preview=preview
        )
    except Exception as exc:  # noqa: BLE001
        _warn("Conversation metadata update failed", exc)
