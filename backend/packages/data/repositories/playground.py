"""Playground build-chat sessions (single table + S3 transcript).

A Playground session is one small item (``USER#<userId>`` /
``PGSESSION#<sessionId>``) that records a chat with the code generator while a
user builds one custom MCP server/tool. The bulky transcript — every message,
including the generated code of each proposal — lives in S3
(``retrieval.layout.playground_key``); the item carries only the metadata the
switcher and history list need.

Access patterns:

* by id (owner)      GetItem on ``USER#<userId>`` / ``PGSESSION#<id>`` (strong)
* by user (history)  Query GSI2 ``byUser`` on ``PGSESSION#`` prefix, newest first
"""

from __future__ import annotations

from typing import Any

from data.client import now_iso, table
from data.keys import (
    GSI2,
    playground_by_user_sk,
    playground_session_sk,
    user_pk,
)

# Hard caps so one account cannot grow the table (or the S3 transcript) without
# bound. The transcript keeps only the most recent messages.
MAX_PLAYGROUND_SESSIONS_PER_USER = 100
MAX_PLAYGROUND_MESSAGES = 200
MAX_PLAYGROUND_PROMPT_CHARS = 4000


def _clean(item: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` attributes (DynamoDB rejects them)."""
    return {key: value for key, value in item.items() if value is not None}


def _new_item(
    *,
    session_id: str,
    user_id: str,
    title: str,
    server_id: str | None,
    server_slug: str | None,
    tool_id: str | None,
    tool_name: str | None,
    created_at: str,
) -> dict[str, Any]:
    return {
        "pk": user_pk(user_id),
        "sk": playground_session_sk(session_id),
        "entity": "playgroundSession",
        "sessionId": session_id,
        "userId": user_id,
        "title": title,
        "serverId": server_id,
        "serverSlug": server_slug,
        "toolId": tool_id,
        "toolName": tool_name,
        "lastPreview": "",
        "messageCount": 0,
        "createdAt": created_at,
        "updatedAt": created_at,
        GSI2[0]: user_pk(user_id),
        GSI2[1]: playground_by_user_sk(created_at, session_id),
    }


def create_session(
    *,
    user_id: str,
    session_id: str,
    title: str = "",
    server_id: str | None = None,
    server_slug: str | None = None,
    tool_id: str | None = None,
    tool_name: str | None = None,
) -> dict[str, Any]:
    item = _clean(
        _new_item(
            session_id=session_id,
            user_id=user_id,
            title=title,
            server_id=server_id,
            server_slug=server_slug,
            tool_id=tool_id,
            tool_name=tool_name,
            created_at=now_iso(),
        )
    )
    table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    return item


def get_session(user_id: str, session_id: str) -> dict[str, Any] | None:
    response = table().get_item(
        Key={"pk": user_pk(user_id), "sk": playground_session_sk(session_id)}
    )
    return response.get("Item")


def list_sessions(
    user_id: str, limit: int = 50, start_key: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """A user's Playground sessions, newest first."""
    kwargs: dict[str, Any] = {
        "IndexName": "byUser",
        "KeyConditionExpression": "gsi2pk = :pk AND begins_with(gsi2sk, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": user_pk(user_id),
            ":prefix": "PGSESSION#",
        },
        "ScanIndexForward": False,
        "Limit": limit,
    }
    if start_key:
        kwargs["ExclusiveStartKey"] = start_key
    response = table().query(**kwargs)
    return response.get("Items") or [], response.get("LastEvaluatedKey")


def count_sessions(user_id: str) -> int:
    """Total sessions for a user (loops the byUser query; never a Scan)."""
    total = 0
    start_key: dict[str, Any] | None = None
    while True:
        items, start_key = list_sessions(user_id, limit=100, start_key=start_key)
        total += len(items)
        if not start_key:
            return total


def touch_session(
    user_id: str,
    session_id: str,
    *,
    title: str | None = None,
    server_id: str | None = None,
    server_slug: str | None = None,
    tool_id: str | None = None,
    tool_name: str | None = None,
    preview: str | None = None,
    message_count: int | None = None,
) -> None:
    """Refresh recency and any provided metadata after a turn/save (best-effort)."""
    timestamp = now_iso()
    sets = ["updatedAt = :ts", "gsi2sk = :g2"]
    values: dict[str, Any] = {
        ":ts": timestamp,
        ":g2": playground_by_user_sk(timestamp, session_id),
    }
    names: dict[str, str] = {}
    if title is not None:
        sets.append("#title = :title")
        names["#title"] = "title"
        values[":title"] = title
    for attribute, value in (
        ("serverId", server_id),
        ("serverSlug", server_slug),
        ("toolId", tool_id),
        ("toolName", tool_name),
        ("lastPreview", preview[:280] if preview else None),
        ("messageCount", message_count),
    ):
        if value is None:
            continue
        sets.append(f"{attribute} = :{attribute}")
        values[f":{attribute}"] = value
    kwargs: dict[str, Any] = {
        "Key": {"pk": user_pk(user_id), "sk": playground_session_sk(session_id)},
        "UpdateExpression": "SET " + ", ".join(sets),
        "ExpressionAttributeValues": values,
        "ConditionExpression": "attribute_exists(pk)",
    }
    if names:
        kwargs["ExpressionAttributeNames"] = names
    table().update_item(**kwargs)


def delete_session(user_id: str, session_id: str) -> dict[str, Any] | None:
    response = table().delete_item(
        Key={"pk": user_pk(user_id), "sk": playground_session_sk(session_id)},
        ReturnValues="ALL_OLD",
    )
    return response.get("Attributes")
