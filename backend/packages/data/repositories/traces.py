"""Agent-run traces (Langfuse-style observability, AWS-native).

A run's **full observation tree** lives in one S3 object
(``retrieval.layout.trace_key``); a tiny **index item** lives in the shared
DynamoDB table so the trace list is one Query with no S3 reads:

    Trace index   USER#<userId>   TRACE#<traceId>
    GSI2 byUser   USER#<userId>   TRACE#<startedAt>#<traceId>   (recency list)
    GSI1 byId     TRACEAGENT#<id> <startedAt>#<traceId>         (per-agent filter)

The index carries only small, filterable metadata (agent, model, status,
latency, tokens, cost, tags, previews, span count). The bulky input/output of
each observation stays in S3. Items carry a TTL (``expiresAt``) so the store
self-prunes. Never a Scan: the list is always a Query on GSI2/GSI1.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from data.client import now_iso, table, ttl_epoch
from data.keys import (
    TRACE_PREFIX,
    trace_agent_pk,
    trace_by_agent_sk,
    trace_by_user_sk,
    trace_sk,
    user_pk,
)

# Traces are retained for this long, then DynamoDB TTL removes the index item.
# The S3 tree is removed with it by the same expiry lifecycle (best-effort).
TTL_DAYS = 90
MAX_LIST = 100
MAX_PREVIEW = 400


class TraceStoreError(RuntimeError):
    """A trace index operation failed."""


def _clip(value: Any, limit: int = MAX_PREVIEW) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = str(text or "")
    return text[:limit]


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
        return json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except Exception:  # noqa: BLE001 - a bad cursor restarts the list
        return None


def _index_item(user_id: str, trace: dict[str, Any]) -> dict[str, Any]:
    trace_id = str(trace.get("traceId") or trace.get("id") or "")
    started_at = str(trace.get("startedAt") or now_iso())
    item: dict[str, Any] = {
        "pk": user_pk(user_id),
        "sk": trace_sk(trace_id),
        "entity": "trace",
        "userId": user_id,
        "traceId": trace_id,
        "name": str(trace.get("name") or "agent run"),
        "startedAt": started_at,
        "createdAt": trace.get("createdAt") or started_at,
        "gsi2pk": user_pk(user_id),
        "gsi2sk": trace_by_user_sk(started_at, trace_id),
        "expiresAt": ttl_epoch(TTL_DAYS),
    }
    agent_id = str(trace.get("agentId") or "")
    if agent_id:
        item["gsi1pk"] = trace_agent_pk(agent_id)
        item["gsi1sk"] = trace_by_agent_sk(started_at, trace_id)
    # Copy the small metadata fields, clipping the previews.
    item["agentId"] = agent_id
    item["agentName"] = str(trace.get("agentName") or "")
    item["model"] = str(trace.get("model") or "")
    item["provider"] = trace.get("provider")
    item["status"] = str(trace.get("status") or "ok")
    item["level"] = str(trace.get("level") or "DEFAULT")
    item["statusMessage"] = trace.get("statusMessage")
    item["endedAt"] = trace.get("endedAt")
    item["latencyMs"] = trace.get("latencyMs")
    item["tags"] = [str(tag) for tag in (trace.get("tags") or [])]
    item["inputPreview"] = _clip(trace.get("input"))
    item["outputPreview"] = _clip(trace.get("output"))
    item["usage"] = trace.get("usage") or {}
    item["costMicroUsd"] = int(trace.get("costMicroUsd") or 0)
    item["observationCount"] = int(trace.get("observationCount") or 0)
    item["sessionId"] = trace.get("sessionId")
    item["conversationId"] = trace.get("conversationId")
    item["runId"] = trace.get("runId")
    # The full tree is dropped before the index write; never store it twice.
    item.pop("observations", None)
    return item


def save_trace_index(user_id: str, trace: dict[str, Any]) -> dict[str, Any]:
    """Upsert one trace's small index item (the S3 tree is written separately)."""
    if not user_id or not trace:
        raise TraceStoreError("save_trace_index needs a user and a trace")
    item = _index_item(user_id, trace)
    try:
        table().put_item(Item=item)
    except Exception as exc:  # noqa: BLE001
        raise TraceStoreError(f"trace index write failed: {exc}") from exc
    return item


def get_trace_index(user_id: str, trace_id: str) -> dict[str, Any] | None:
    try:
        response = table().get_item(
            Key={"pk": user_pk(user_id), "sk": trace_sk(trace_id)}
        )
    except Exception as exc:  # noqa: BLE001
        raise TraceStoreError(f"trace index read failed: {exc}") from exc
    item = response.get("Item")
    if item is not None:
        item.pop("input", None)
        item.pop("output", None)
    return item


def list_traces(
    user_id: str,
    *,
    limit: int = 25,
    cursor: str | None = None,
    agent_id: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Newest-first traces for a user (one GSI Query, never a Scan).

    ``agent_id`` narrows to one agent via the overloaded GSI1 partition.
    """
    from boto3.dynamodb.conditions import Key

    bounded = max(1, min(int(limit), MAX_LIST))
    start_key = decode_cursor(cursor)
    if agent_id:
        condition = Key("gsi1pk").eq(trace_agent_pk(agent_id))
        index = "byId"
    else:
        condition = Key("gsi2pk").eq(user_pk(user_id)) & Key("gsi2sk").begins_with(
            TRACE_PREFIX
        )
        index = "byUser"
    kwargs: dict[str, Any] = {
        "IndexName": index,
        "KeyConditionExpression": condition,
        "ScanIndexForward": False,
        "Limit": bounded,
    }
    if start_key:
        kwargs["ExclusiveStartKey"] = start_key
    try:
        response = table().query(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise TraceStoreError(f"trace list failed: {exc}") from exc
    items = response.get("Items") or []
    for item in items:
        item.pop("input", None)
        item.pop("output", None)
    return items, encode_cursor(response.get("LastEvaluatedKey"))


def delete_traces(user_id: str) -> int:
    """Delete every trace index item for a user (account erasure)."""
    from boto3.dynamodb.conditions import Key

    removed = 0
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": Key("pk").eq(user_pk(user_id))
        & Key("sk").begins_with(TRACE_PREFIX),
    }
    while True:
        response = table().query(**kwargs)
        for item in response.get("Items") or []:
            table().delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
            removed += 1
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return removed
