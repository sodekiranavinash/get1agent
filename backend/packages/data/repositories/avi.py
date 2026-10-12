"""Avi (in-product assistant) persistence: conversations, feedback, traces, evals.

Avi deliberately keeps **its own prefixes** so nothing it writes can surface in
the agent surfaces:

    Conversation   USER#<userId>   AVICHAT#<id>          (+ GSI2 byUser)
    Feedback       USER#<userId>   AVIFEEDBACK#<runId>
    Trace index    USER#<userId>   AVITRACE#<traceId>    (+ GSI2 byUser)
    Eval run       USER#<userId>   AVIEVAL#<runId>

The bulky parts live in S3, exactly like the agent equivalents:

* a conversation transcript is **one JSON object** per conversation
  (``retrieval.layout.conversation_key``) — read-modify-write once per turn;
* a run's **full observation tree** is one JSON object
  (``retrieval.layout.trace_key``), with only small filterable metadata in the
  index item so the admin list is one Query and never an S3 read.

Conversation ids are opaque, time-sortable strings (``avi_<epoch_ms>_<rand>``)
rather than the global chat counter: a guest's thread is never stored, and a
signed-in user's Avi threads are private, so there is nothing to order globally.

Everything here is best-effort on the write path (a persistence failure must
never cost the user an answer) and strictly owner-scoped on the read path.
"""

from __future__ import annotations

import base64
import json
import secrets
import time
from decimal import Decimal
from typing import Any

from core.storage import Storage
from data.client import now_iso, table, ttl_epoch
from data.keys import (
    AVI_CHAT_PREFIX,
    AVI_EVAL_RUN_PREFIX,
    AVI_FEEDBACK_PREFIX,
    AVI_TRACE_PREFIX,
    avi_chat_by_user_sk,
    avi_chat_sk,
    avi_eval_run_sk,
    avi_feedback_sk,
    avi_trace_by_user_sk,
    avi_trace_sk,
    user_pk,
)
from retrieval.layout import conversation_key, trace_key

GSI_BY_USER = "byUser"

# Traces self-prune; conversations and feedback are small and long-lived.
TRACE_TTL_DAYS = 90
MAX_LIST = 100
MAX_PREVIEW = 400
MAX_COMMENT = 2_000
MAX_CATEGORIES = 12
MAX_SOURCES = 20
MAX_TRANSCRIPT_TURNS = 200

VALUE_UP = "up"
VALUE_DOWN = "down"
VALUES = (VALUE_UP, VALUE_DOWN)

# What the classifier decided — stored on feedback and traces so
# "did we refuse something we should have answered?" is one Query.
KIND_PLATFORM = "platform"
KIND_OFF_TOPIC = "off_topic"
KIND_UNSAFE = "unsafe"


class AviStoreError(RuntimeError):
    """An Avi persistence operation failed."""


def _storage() -> Storage:
    """The S3 object store (a no-op double when ``S3_BUCKET`` is unset)."""
    return Storage()


def _clip(value: Any, limit: int = MAX_PREVIEW) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return str(text or "")[:limit]


def new_conversation_id() -> str:
    """A sortable, unguessable Avi conversation id."""
    return f"avi_{int(time.time() * 1000):013d}_{secrets.token_hex(4)}"


def new_run_id() -> str:
    """A per-answer id — the key feedback and traces hang off."""
    return f"avirun_{int(time.time() * 1000):013d}_{secrets.token_hex(4)}"


def encode_cursor(key: dict[str, Any] | None) -> str | None:
    """Opaque pagination cursor from a DynamoDB ``LastEvaluatedKey``."""
    if not key:
        return None
    try:
        raw = json.dumps(key, separators=(",", ":")).encode()
    except (TypeError, ValueError):
        return None
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
    except Exception:  # noqa: BLE001 - a bad cursor just means "from the start"
        return None


# --- conversations ------------------------------------------------------------


def create_conversation(
    user_id: str,
    *,
    title: str = "",
    entry_route: str = "",
    model: str = "",
    client: str = "web",
) -> dict[str, Any]:
    """Create an Avi conversation (one metadata item; transcript starts empty)."""
    conversation_id = new_conversation_id()
    timestamp = now_iso()
    item: dict[str, Any] = {
        "pk": user_pk(user_id),
        "sk": avi_chat_sk(conversation_id),
        "entity": "avi-conversation",
        "conversationId": conversation_id,
        "userId": user_id,
        "title": (title or "")[:120],
        "entryRoute": entry_route or "",
        "model": model or "",
        "client": client,
        "messageCount": 0,
        "turnCount": 0,
        "lastPreview": "",
        "lastIntent": "",
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "gsi2pk": user_pk(user_id),
        "gsi2sk": avi_chat_by_user_sk(timestamp, conversation_id),
    }
    table().put_item(Item=item)
    # Best-effort: seed the empty transcript so the first turn is an append.
    try:
        _storage().put_json(conversation_key(user_id, conversation_id), {"turns": []})
    except Exception:  # noqa: BLE001 - the transcript is never on the critical path
        pass
    return item


def get_conversation(user_id: str, conversation_id: str) -> dict[str, Any] | None:
    return table().get_item(
        Key={"pk": user_pk(user_id), "sk": avi_chat_sk(conversation_id)}
    ).get("Item")


def list_conversations(
    user_id: str, limit: int = 50, start_key: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """A user's Avi conversations, newest first (admin → Avi viewer)."""
    kwargs: dict[str, Any] = {
        "IndexName": GSI_BY_USER,
        "KeyConditionExpression": "gsi2pk = :pk AND begins_with(gsi2sk, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": user_pk(user_id),
            ":prefix": AVI_CHAT_PREFIX,
        },
        "ScanIndexForward": False,
        "Limit": max(1, min(limit, MAX_LIST)),
    }
    if start_key:
        kwargs["ExclusiveStartKey"] = start_key
    response = table().query(**kwargs)
    return response.get("Items") or [], response.get("LastEvaluatedKey")


def update_conversation(user_id: str, conversation_id: str, **fields: Any) -> None:
    """Patch conversation metadata (counts, preview, title, last intent)."""
    allowed = (
        "title",
        "messageCount",
        "turnCount",
        "lastPreview",
        "lastIntent",
        "model",
    )
    patch = {key: value for key, value in fields.items() if key in allowed}
    if not patch:
        return

    assignments = ["updatedAt = :updatedAt"]
    values: dict[str, Any] = {":updatedAt": now_iso()}
    for index, (key, value) in enumerate(patch.items()):
        placeholder = f":v{index}"
        assignments.append(f"{key} = {placeholder}")
        values[placeholder] = value

    table().update_item(
        Key={"pk": user_pk(user_id), "sk": avi_chat_sk(conversation_id)},
        UpdateExpression="SET " + ", ".join(assignments),
        ExpressionAttributeValues=values,
    )


def touch_conversation(
    user_id: str, conversation_id: str, *, updated_at: str | None = None
) -> None:
    """Refresh the byUser sort key so the admin list stays recency-ordered."""
    timestamp = updated_at or now_iso()
    table().update_item(
        Key={"pk": user_pk(user_id), "sk": avi_chat_sk(conversation_id)},
        UpdateExpression="SET updatedAt = :t, gsi2sk = :sk",
        ExpressionAttributeValues={
            ":t": timestamp,
            ":sk": avi_chat_by_user_sk(timestamp, conversation_id),
        },
    )


def delete_conversation(user_id: str, conversation_id: str) -> None:
    table().delete_item(Key={"pk": user_pk(user_id), "sk": avi_chat_sk(conversation_id)})
    try:
        _storage().delete(conversation_key(user_id, conversation_id))
    except Exception:  # noqa: BLE001
        pass


def get_transcript(user_id: str, conversation_id: str) -> dict[str, Any]:
    """The stored transcript (``{"turns": [...]}``), or an empty skeleton."""
    try:
        data = _storage().get_json(conversation_key(user_id, conversation_id))
    except Exception:  # noqa: BLE001
        data = None
    if not isinstance(data, dict):
        return {"turns": []}
    if not isinstance(data.get("turns"), list):
        data["turns"] = []
    return data


def append_turn(user_id: str, conversation_id: str, turn: dict[str, Any]) -> None:
    """Append one turn to the S3 transcript and refresh the metadata item.

    The browser always sends the full conversation, so this transcript is for
    replay, admin review and evaluation — never the source of truth for a turn.
    """
    storage = _storage()
    key = conversation_key(user_id, conversation_id)
    data = storage.get_json(key) or {}
    turns = data.get("turns")
    if not isinstance(turns, list):
        turns = []
    turns.append(turn)
    storage.put_json(key, {"turns": turns[-MAX_TRANSCRIPT_TURNS:]})

    summary: dict[str, Any] = {
        "messageCount": len(turns) * 2,
        "turnCount": len(turns),
        "lastPreview": _clip(turn.get("answer") or turn.get("question") or ""),
    }
    if turn.get("intent"):
        summary["lastIntent"] = str(turn["intent"])[:40]
    # Seed the title from the first question, like the chat sidebar does.
    if len(turns) == 1 and turn.get("question") and not turn.get("title"):
        summary["title"] = str(turn["question"])[:120]
    try:
        update_conversation(user_id, conversation_id, **summary)
        touch_conversation(user_id, conversation_id)
    except Exception:  # noqa: BLE001 - metadata is best-effort
        pass


# --- feedback -----------------------------------------------------------------


def upsert_feedback(
    user_id: str,
    run_id: str,
    *,
    value: str,
    comment: str = "",
    categories: list[str] | None = None,
    conversation_id: str = "",
    message_id: str = "",
    question: str = "",
    answer_preview: str = "",
    sources: list[dict[str, Any]] | None = None,
    route_clicked: str = "",
    model: str = "",
    classifier_kind: str = "",
    intent: str = "",
    latency_ms: int | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_micro_usd: int | None = None,
    trace_id: str = "",
) -> dict[str, Any]:
    """Create or update feedback for one Avi answer.

    Unlike the agent feedback item (thumbs + comment only), an Avi feedback item
    carries the question, the answer preview, the sources used, the classifier's
    verdict and the cost/latency — everything the admin feedback table needs
    without a second lookup.
    """
    if value not in VALUES:
        raise ValueError(f"value must be one of {VALUES}")

    timestamp = now_iso()
    item: dict[str, Any] = {
        "pk": user_pk(user_id),
        "sk": avi_feedback_sk(run_id),
        "entity": "avi-feedback",
        "runId": run_id,
        "userId": user_id,
        "value": value,
        "comment": str(comment or "")[:MAX_COMMENT],
        "categories": [str(c)[:64] for c in (categories or [])][:MAX_CATEGORIES],
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }
    for key, raw in (
        ("conversationId", conversation_id),
        ("messageId", message_id),
        ("question", _clip(question, 1_000)),
        ("answerPreview", _clip(answer_preview, 1_000)),
        ("routeClicked", route_clicked),
        ("model", model),
        ("classifierKind", classifier_kind),
        ("intent", intent),
        ("traceId", trace_id),
    ):
        if raw not in (None, "", [], {}):
            item[key] = raw
    for key, raw in (
        ("latencyMs", latency_ms),
        ("tokensIn", tokens_in),
        ("tokensOut", tokens_out),
        ("costMicroUsd", cost_micro_usd),
    ):
        if raw is not None:
            item[key] = int(raw)
    if sources:
        item["sources"] = json.loads(json.dumps(sources[:MAX_SOURCES], default=str))

    table().put_item(Item=item)
    return item


def record_feedback(user_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Validate and store one Avi thumb from a request body.

    This is the **single** normalizer for Avi feedback, kept here rather than in
    either caller because there are two of them: the Avi agent service's
    ``POST /feedback`` (reachable only through the MicroVM ingress) and
    ``user-api``'s ``POST /v1/avi/feedback`` (how the browser actually reaches it,
    since it cannot mint the MicroVM ingress token). Two implementations would
    drift, and the admin feedback table would show whichever one was used last.

    Returns the stored item. Raises ``ValueError`` for a body a caller should see
    as a 400.
    """
    value = str(body.get("value") or "").strip().lower()
    if value not in VALUES:
        raise ValueError("value must be 'up' or 'down'")

    run_id = str(body.get("runId") or body.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("runId is required")
    run_id = run_id[:120]

    sources: list[dict[str, Any]] = []
    for item in body.get("sources") or []:
        if isinstance(item, dict):
            sources.append(
                {
                    "title": str(item.get("title") or "")[:200],
                    "route": str(item.get("route") or "")[:200],
                }
            )

    def as_int(name: str) -> int | None:
        try:
            raw = body.get(name)
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    return upsert_feedback(
        user_id,
        run_id,
        value=value,
        comment=str(body.get("comment") or ""),
        categories=[str(item)[:64] for item in (body.get("categories") or []) if item],
        conversation_id=str(body.get("conversationId") or "")[:120],
        message_id=str(body.get("messageId") or "")[:120],
        question=str(body.get("question") or "")[:1_000],
        answer_preview=str(body.get("answerPreview") or body.get("answer") or "")[:1_000],
        sources=sources,
        route_clicked=str(body.get("routeClicked") or "")[:200],
        model=str(body.get("model") or "")[:120],
        classifier_kind=str(body.get("classifierKind") or "")[:32],
        intent=str(body.get("intent") or "")[:40],
        latency_ms=as_int("latencyMs"),
        tokens_in=as_int("tokensIn"),
        tokens_out=as_int("tokensOut"),
        cost_micro_usd=as_int("costMicroUsd"),
        trace_id=str(body.get("traceId") or "")[:120],
    )


def get_feedback(user_id: str, run_id: str) -> dict[str, Any] | None:
    return table().get_item(
        Key={"pk": user_pk(user_id), "sk": avi_feedback_sk(run_id)}
    ).get("Item")


def delete_feedback(user_id: str, run_id: str) -> None:
    table().delete_item(Key={"pk": user_pk(user_id), "sk": avi_feedback_sk(run_id)})


def list_feedback(
    user_id: str,
    *,
    limit: int = 50,
    value: str | None = None,
    start_key: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """A user's Avi feedback, newest first (prefix Query, never a Scan)."""
    values: dict[str, Any] = {
        ":pk": user_pk(user_id),
        ":prefix": AVI_FEEDBACK_PREFIX,
    }
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": values,
        "ScanIndexForward": False,
        "Limit": max(1, min(limit, MAX_LIST)),
    }
    if value in VALUES:
        kwargs["FilterExpression"] = "#v = :value"
        kwargs["ExpressionAttributeNames"] = {"#v": "value"}
        values[":value"] = value
    if start_key:
        kwargs["ExclusiveStartKey"] = start_key
    response = table().query(**kwargs)
    return response.get("Items") or [], response.get("LastEvaluatedKey")


# --- traces -------------------------------------------------------------------


def put_trace(
    user_id: str,
    trace_id: str,
    *,
    tree: dict[str, Any],
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist one Avi run's trace: the tree in S3, a small index item in DDB."""
    storage = _storage()
    key = trace_key(user_id, trace_id)
    payload = dict(tree or {})
    payload.setdefault("traceId", trace_id)
    storage.put_json(key, payload)

    timestamp = now_iso()
    item: dict[str, Any] = {
        "pk": user_pk(user_id),
        "sk": avi_trace_sk(trace_id),
        "entity": "avi-trace",
        "traceId": trace_id,
        "userId": user_id,
        "createdAt": timestamp,
        "expiresAt": ttl_epoch(TRACE_TTL_DAYS),
        "s3Key": key,
        "gsi2pk": user_pk(user_id),
        "gsi2sk": avi_trace_by_user_sk(timestamp, trace_id),
    }
    for field in (
        "question",
        "answerPreview",
        "model",
        "classifierKind",
        "intent",
        "status",
        "latencyMs",
        "ttftMs",
        "tokensIn",
        "tokensOut",
        "costMicroUsd",
        "sourceCount",
        "spanCount",
        "conversationId",
        "runId",
        "entryRoute",
        "stopReason",
    ):
        raw = (summary or {}).get(field)
        if raw not in (None, "", [], {}):
            item[field] = _clip(raw, 1_000) if field == "question" else raw

    table().put_item(Item=item)
    return item


def get_trace(user_id: str, trace_id: str) -> dict[str, Any] | None:
    item = table().get_item(
        Key={"pk": user_pk(user_id), "sk": avi_trace_sk(trace_id)}
    ).get("Item")
    if not item:
        return None
    return {**item, "tree": _read_trace_tree(item)}


def _read_trace_tree(item: dict[str, Any]) -> dict[str, Any] | None:
    key = str(item.get("s3Key") or "")
    if not key:
        return None
    try:
        data = _storage().get_json(key)
    except Exception:  # noqa: BLE001 - the index item still renders a summary
        return None
    return data if isinstance(data, dict) else None


def list_traces(
    user_id: str, limit: int = 50, start_key: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """A user's Avi traces, newest first (admin → Avi trace list)."""
    kwargs: dict[str, Any] = {
        "IndexName": GSI_BY_USER,
        "KeyConditionExpression": "gsi2pk = :pk AND begins_with(gsi2sk, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": user_pk(user_id),
            ":prefix": AVI_TRACE_PREFIX,
        },
        "ScanIndexForward": False,
        "Limit": max(1, min(limit, MAX_LIST)),
    }
    if start_key:
        kwargs["ExclusiveStartKey"] = start_key
    response = table().query(**kwargs)
    return response.get("Items") or [], response.get("LastEvaluatedKey")


def delete_trace(user_id: str, trace_id: str) -> None:
    item = table().get_item(
        Key={"pk": user_pk(user_id), "sk": avi_trace_sk(trace_id)}
    ).get("Item") or {}
    table().delete_item(Key={"pk": user_pk(user_id), "sk": avi_trace_sk(trace_id)})
    key = str(item.get("s3Key") or "")
    if key:
        try:
            _storage().delete(key)
        except Exception:  # noqa: BLE001
            pass


# --- evaluation runs ----------------------------------------------------------


def _dynamo_safe(value: Any) -> Any:
    """Make a JSON-shaped payload writable to DynamoDB.

    The evaluation worker hands us native JSON (so floats), but DynamoDB rejects
    float — scores must land as ``Decimal`` or the write fails. Converting here
    keeps the repository usable with plain JSON in and out, and the JSON round
    trip drops anything boto3 could not serialise anyway.
    """
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _dynamo_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_dynamo_safe(item) for item in value]
    return value


def _avi_eval_by_user_sk(created_at: str, run_id: str) -> str:
    """GSI2 ``byUser`` sort key: Avi eval runs, newest first."""
    return f"{AVI_EVAL_RUN_PREFIX}{created_at}#{run_id}"


def put_eval_run(user_id: str, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist an Avi evaluation run (the admin run history)."""
    timestamp = now_iso()
    item: dict[str, Any] = {
        "pk": user_pk(user_id),
        "sk": avi_eval_run_sk(run_id),
        "entity": "avi-eval-run",
        "runId": run_id,
        "userId": user_id,
        "createdAt": timestamp,
        "gsi2pk": user_pk(user_id),
        "gsi2sk": _avi_eval_by_user_sk(timestamp, run_id),
    }
    item.update(_dynamo_safe(json.loads(json.dumps(payload or {}, default=str))))
    table().put_item(Item=item)
    return item


def get_eval_run(user_id: str, run_id: str) -> dict[str, Any] | None:
    return table().get_item(
        Key={"pk": user_pk(user_id), "sk": avi_eval_run_sk(run_id)}
    ).get("Item")


def list_eval_runs(
    user_id: str, limit: int = 20, start_key: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    kwargs: dict[str, Any] = {
        "IndexName": GSI_BY_USER,
        "KeyConditionExpression": "gsi2pk = :pk AND begins_with(gsi2sk, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": user_pk(user_id),
            ":prefix": AVI_EVAL_RUN_PREFIX,
        },
        "ScanIndexForward": False,
        "Limit": max(1, min(limit, MAX_LIST)),
    }
    if start_key:
        kwargs["ExclusiveStartKey"] = start_key
    response = table().query(**kwargs)
    return response.get("Items") or [], response.get("LastEvaluatedKey")
