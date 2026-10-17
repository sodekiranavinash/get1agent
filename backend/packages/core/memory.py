"""AgentCore Memory read/write/erase helpers, shared by ``user-api`` and the runtime.

The deployed backend is Amazon **Bedrock AgentCore Memory** (managed long-term
memory, one resource per deployment). ``MEMORY_BACKEND=dynamo`` selects the
in-app DynamoDB + S3 Vectors fallback used by Floci and tests.

This module deliberately talks to the AgentCore data plane with **raw boto3**
(not the ``bedrock_agentcore`` SDK) so every Lambda can use it without an extra
dependency. Every record lives under the caller's own namespace
``/users/<userId>/``, so a user can only ever list or erase their own memory.

AgentCore Memory APIs used:

* ``list_memory_records`` / ``retrieve_memory_records`` (read)
* ``batch_create_memory_records`` (write a consolidated record directly)
* ``delete_memory_record`` / ``batch_delete_memory_records`` (erase long term)
* ``list_sessions`` / ``list_events`` / ``delete_event`` (erase short term)

**``namespace`` is an exact match, ``namespacePath`` is the subtree.** Records
live one level below the user root (``/users/<id>/facts/``,
``/users/<id>/preferences/``), so every read and erase here must pass
``namespacePath`` — an exact match on the root matches nothing.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

#: ``content.text`` is capped at 16000 by the service. A memory should be a
#: sentence, not a document, so we keep the tool honest at a much smaller size.
MAX_RECORD_CHARS = 2000

#: The strategy namespaces provisioned by Terraform, by kind of memory. Writing
#: to one does not gate retrieval (both live under the user root and rank
#: together) — it only decides how the record is filed.
_KIND_LEAF = {"preference": "preferences", "fact": "facts"}

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


def record_namespace(user_id: str, kind: str = "preference") -> str:
    """The namespace a new record is filed under for this kind of memory.

    These are the templates provisioned as AgentCore Memory strategies
    (``/users/{actorId}/preferences/`` for USER_PREFERENCE, ``/users/{actorId}/``
    ``facts/`` for SEMANTIC). An unknown kind falls back to preferences.
    """
    leaf = _KIND_LEAF.get((kind or "").strip().lower(), "preferences")
    return f"{user_namespace(user_id)}{leaf}/"


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


def _error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None) or {}
    return str((response.get("Error") or {}).get("Code") or "")


def _error_message(exc: Exception) -> str:
    response = getattr(exc, "response", None) or {}
    return str((response.get("Error") or {}).get("Message") or "")


def _is_not_found(exc: Exception) -> bool:
    """A missing actor/session/record is an empty result, not a failure.

    ``list_sessions`` raises ``ResourceNotFoundException`` for an actor that has
    no short-term events — which is the normal case for a user whose memory is
    only ever written directly — and that must not fail an erasure.
    """
    return _error_code(exc) == "ResourceNotFoundException"


def _is_duplicate_write(exc: Exception) -> bool:
    """A replayed ``clientToken`` whose body differs only by its timestamp.

    ``clientToken`` is the idempotency key, so the service refuses a second
    request carrying the same token with a different body — the earlier write
    already succeeded and the record exists, so this is a no-op rather than an
    error. (``timestamp`` is the only field that differs on a legitimate retry:
    the token itself is a hash of user, namespace and text.)
    """
    return _error_code(exc) == "ValidationException" and (
        "Parameter hash does not match" in _error_message(exc)
    )


def _agentcore_list(user_id: str, *, cursor: str | None, limit: int, query: str | None) -> dict[str, Any]:
    client = _data_client()
    mid = memory_id()
    # ``namespacePath`` (subtree), never ``namespace`` (exact): records live one
    # level down, so an exact match on the user root returns nothing.
    namespace_path = user_namespace(user_id)
    size = max(1, min(int(limit or 50), 100))
    if query:
        response = client.retrieve_memory_records(
            memoryId=mid,
            namespacePath=namespace_path,
            searchCriteria={"searchQuery": query, "topK": size},
        )
    else:
        kwargs: dict[str, Any] = {
            "memoryId": mid,
            "namespacePath": namespace_path,
            "maxResults": size,
        }
        if cursor:
            kwargs["nextToken"] = cursor
        response = client.list_memory_records(**kwargs)
    records = response.get("memoryRecordSummaries") or []
    return {
        "records": [_shape(record) for record in records],
        "nextCursor": None if query else response.get("nextToken"),
    }


def save_record(user_id: str, text: str, *, kind: str = "preference") -> dict[str, Any]:
    """Write one durable long-term record, readable within a couple of seconds.

    ``batch_create_memory_records`` writes the consolidated record **directly**
    instead of waiting for the asynchronous extraction that ``create_event``
    triggers, which is what makes "remember this" recallable in the same
    conversation rather than minutes later.

    The ``clientToken`` is a deterministic hash of (user, namespace, text), so a
    retried write is deduplicated by the service. ``requestIdentifier`` alone is
    **not** an idempotency key — reusing it creates a second record.

    AgentCore only: the local DynamoDB fallback writes through its own store.
    """
    if not is_agentcore():
        raise RuntimeError(
            "save_record needs the managed AgentCore backend (AGENTCORE_MEMORY_ID)"
        )
    body = (text or "").strip()
    if not body:
        raise ValueError("text is required")
    body = body[:MAX_RECORD_CHARS]
    namespace = record_namespace(user_id, kind)
    token = hashlib.sha256(f"{user_id}\x00{namespace}\x00{body}".encode()).hexdigest()
    try:
        response = _data_client().batch_create_memory_records(
            memoryId=memory_id(),
            clientToken=token,
            records=[
                {
                    "requestIdentifier": token,
                    "namespaces": [namespace],
                    "content": {"text": body},
                    "timestamp": datetime.now(timezone.utc),
                }
            ],
        )
    except Exception as exc:  # noqa: BLE001 - reported to the caller below
        if _is_duplicate_write(exc):
            # The same memory was written before; it is already there.
            return {
                "id": "",
                "namespace": namespace,
                "text": body,
                "failed": [],
                "duplicate": True,
            }
        raise
    created = (response.get("successfulRecords") or [{}])[0]
    return {
        "id": str(created.get("memoryRecordId") or ""),
        "namespace": namespace,
        "text": body,
        "failed": response.get("failedRecords") or [],
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
        # Subtree, not exact: otherwise erasure silently skips every record and
        # leaves the user's memory behind after an account deletion.
        kwargs: dict[str, Any] = {
            "memoryId": mid,
            "namespacePath": namespace,
            "maxResults": 100,
        }
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
        try:
            sessions = client.list_sessions(**kwargs)
        except Exception as exc:  # noqa: BLE001
            # An actor with no short-term events has no session list at all.
            if _is_not_found(exc):
                break
            raise
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
                try:
                    events = client.list_events(**event_kwargs)
                except Exception as exc:  # noqa: BLE001
                    if _is_not_found(exc):
                        break
                    raise
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
