"""AgentCore Memory read/erase helpers, shared by ``user-api`` and the runtime.

The deployed backend is Amazon **Bedrock AgentCore Memory** (managed long-term
memory, one resource per deployment). ``MEMORY_BACKEND=dynamo`` selects the
in-app DynamoDB + S3 Vectors fallback used by Floci and tests.

This module deliberately talks to the AgentCore data plane with **raw boto3**
(not the ``bedrock_agentcore`` SDK) so every Lambda can use it without an extra
dependency. Every record lives under the caller's own namespace
``/users/<userId>/``, so a user can only ever list or erase their own memory.

AgentCore Memory APIs used:

* ``list_memory_records`` / ``retrieve_memory_records`` (read)
* ``delete_memory_record`` / ``batch_delete_memory_records`` (erase long term)
* ``list_sessions`` / ``list_events`` / ``delete_event`` (erase short term)
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

MEMORY_DYNAMO = "dynamo"
MEM_PREFIX = "MEM#"


def backend() -> str:
    return (
        os.environ.get("MEMORY_BACKEND")
        or os.environ.get("AGENT_MEMORY_BACKEND")
        or "agentcore"
    ).strip().lower()


def region() -> str:
    return (
        os.environ.get("AGENTCORE_MEMORY_REGION")
        or os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or "ap-south-1"
    ).strip()


def memory_id() -> str:
    return (os.environ.get("AGENTCORE_MEMORY_ID") or "").strip()


def is_agentcore() -> bool:
    """True when the managed backend is configured for this environment."""
    return backend() != MEMORY_DYNAMO and bool(memory_id())


def user_namespace(user_id: str) -> str:
    """The user-scoped namespace prefix every record for this user lives under."""
    return f"/users/{user_id}/"


def memory_enabled(user_id: str) -> bool:
    """Whether cross-session memory is on for this user (workspace default: on).

    Reads the settings item's ``memoryEnabled`` flag; absent means enabled, so
    memory works out of the box and a user opts out only deliberately.
    """
    try:
        from data.repositories import settings as settings_repo

        settings = settings_repo.get_settings(user_id)
    except Exception:  # noqa: BLE001 - a settings read must never break a run
        return True
    value = settings.get("memoryEnabled")
    return True if value is None else bool(value)


# --- AgentCore data plane ----------------------------------------------------


def _data_client():
    import boto3

    return boto3.client("bedrock-agentcore", region_name=region())


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None else None


def _shape(record: dict[str, Any]) -> dict[str, Any]:
    content = record.get("content")
    text = ""
    if isinstance(content, dict):
        text = str(content.get("text") or "")
    return {
        "id": str(record.get("memoryRecordId") or ""),
        "text": text,
        "namespaces": list(record.get("namespaces") or []),
        "strategyId": record.get("memoryStrategyId"),
        "score": record.get("score"),
        "createdAt": _iso(record.get("createdAt")),
    }


def _agentcore_list(user_id: str, *, cursor: str | None, limit: int, query: str | None) -> dict[str, Any]:
    client = _data_client()
    mid = memory_id()
    namespace = user_namespace(user_id)
    size = max(1, min(int(limit or 50), 100))
    if query:
        response = client.retrieve_memory_records(
            memoryId=mid,
            namespace=namespace,
            searchCriteria={"searchQuery": query, "topK": size},
        )
    else:
        kwargs: dict[str, Any] = {"memoryId": mid, "namespace": namespace, "maxResults": size}
        if cursor:
            kwargs["nextToken"] = cursor
        response = client.list_memory_records(**kwargs)
    records = response.get("memoryRecordSummaries") or []
    return {
        "records": [_shape(record) for record in records],
        "nextCursor": None if query else response.get("nextToken"),
    }


def _agentcore_delete(user_id: str, record_id: str, namespace: str | None) -> None:
    _data_client().delete_memory_record(
        memoryId=memory_id(),
        memoryRecordId=record_id,
        namespace=namespace or user_namespace(user_id),
    )


def _agentcore_erase_all(user_id: str) -> dict[str, int]:
    client = _data_client()
    mid = memory_id()
    namespace = user_namespace(user_id)

    deleted_records = 0
    cursor: str | None = None
    while True:
        kwargs: dict[str, Any] = {"memoryId": mid, "namespace": namespace, "maxResults": 100}
        if cursor:
            kwargs["nextToken"] = cursor
        response = client.list_memory_records(**kwargs)
        records = response.get("memoryRecordSummaries") or []
        if records:
            batch = [
                {
                    "memoryRecordId": record["memoryRecordId"],
                    "namespace": (record.get("namespaces") or [namespace])[0],
                }
                for record in records
                if record.get("memoryRecordId")
            ]
            if batch:
                client.batch_delete_memory_records(memoryId=mid, records=batch)
                deleted_records += len(batch)
        cursor = response.get("nextToken")
        if not cursor:
            break

    deleted_events = 0
    session_cursor: str | None = None
    while True:
        kwargs = {"memoryId": mid, "actorId": user_id, "maxResults": 100}
        if session_cursor:
            kwargs["nextToken"] = session_cursor
        sessions = client.list_sessions(**kwargs)
        for session in sessions.get("sessionSummaries") or []:
            session_id = str(session.get("sessionId") or "")
            if not session_id:
                continue
            event_cursor: str | None = None
            while True:
                event_kwargs: dict[str, Any] = {
                    "memoryId": mid,
                    "actorId": user_id,
                    "sessionId": session_id,
                    "maxResults": 100,
                }
                if event_cursor:
                    event_kwargs["nextToken"] = event_cursor
                events = client.list_events(**event_kwargs)
                for event in events.get("events") or []:
                    event_id = str(event.get("eventId") or "")
                    if not event_id:
                        continue
                    client.delete_event(
                        memoryId=mid,
                        actorId=user_id,
                        sessionId=session_id,
                        eventId=event_id,
                    )
                    deleted_events += 1
                event_cursor = events.get("nextToken")
                if not event_cursor:
                    break
        session_cursor = sessions.get("nextToken")
        if not session_cursor:
            break

    return {"records": deleted_records, "events": deleted_events}


# --- Local DynamoDB fallback -------------------------------------------------


def _dynamo_items(user_id: str) -> list[dict[str, Any]]:
    from data.client import table
    from data.keys import user_pk

    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": {":pk": user_pk(user_id), ":prefix": MEM_PREFIX},
    }
    items: list[dict[str, Any]] = []
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


def _dynamo_list(user_id: str, *, limit: int, query: str | None) -> dict[str, Any]:
    items = _dynamo_items(user_id)
    needle = (query or "").strip().lower()
    if needle:
        items = [item for item in items if needle in str(item.get("content") or "").lower()]
    items.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    records = [
        {
            "id": str(item.get("memId") or ""),
            "text": str(item.get("content") or ""),
            "namespaces": [user_namespace(user_id)],
            "strategyId": "dynamo",
            "score": None,
            "createdAt": item.get("createdAt"),
        }
        for item in items[: max(1, limit)]
    ]
    return {"records": records, "nextCursor": None}


def _dynamo_delete(user_id: str, record_id: str) -> None:
    from data.client import table
    from data.keys import user_pk

    table().delete_item(Key={"pk": user_pk(user_id), "sk": f"{MEM_PREFIX}{record_id}"})
    _delete_vector(user_id, record_id)


def _delete_vector(user_id: str, record_id: str) -> None:
    try:
        from core.storage import Storage
        from retrieval.s3_vectors import vector_store

        vector_store(Storage()).delete(user_id, [f"mem#{record_id}"])
    except Exception:  # noqa: BLE001 - a stale vector must not block the erase
        pass


def _dynamo_erase_all(user_id: str) -> dict[str, int]:
    from data.client import table

    items = _dynamo_items(user_id)
    for item in items:
        table().delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
        _delete_vector(user_id, str(item.get("memId") or ""))
    return {"records": len(items), "events": 0}


# --- public API --------------------------------------------------------------


def list_records(
    user_id: str,
    *,
    cursor: str | None = None,
    limit: int = 50,
    query: str | None = None,
) -> dict[str, Any]:
    """List (or semantically search) the user's long-term memory records."""
    if not is_agentcore():
        return _dynamo_list(user_id, limit=limit, query=query)
    return _agentcore_list(user_id, cursor=cursor, limit=limit, query=query)


def delete_record(user_id: str, record_id: str, namespace: str | None = None) -> None:
    """Permanently delete one memory record owned by the user."""
    if not is_agentcore():
        _dynamo_delete(user_id, record_id)
        return
    _agentcore_delete(user_id, record_id, namespace)


def erase_all(user_id: str) -> dict[str, int]:
    """Erase every long-term record and short-term event the user owns."""
    if not is_agentcore():
        return _dynamo_erase_all(user_id)
    return _agentcore_erase_all(user_id)


def status() -> dict[str, Any]:
    """Whether the managed backend is configured (for the Memory page header)."""
    info: dict[str, Any] = {
        "backend": "agentcore" if is_agentcore() else "dynamo",
        "configured": is_agentcore(),
        "region": region(),
    }
    if is_agentcore():
        try:
            import boto3

            control = boto3.client("bedrock-agentcore-control", region_name=region())
            memory = control.get_memory(memoryId=memory_id()).get("memory") or {}
            info["status"] = memory.get("status")
        except Exception:  # noqa: BLE001 - status is informational only
            pass
    return info
