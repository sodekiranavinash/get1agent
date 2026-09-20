"""Chat/builder conversations (single table + S3 transcript).

A conversation is one small item (``USER#<userId>`` / ``CHAT#<globalId>``); the
bulky transcript lives in S3 (``retrieval.layout.conversation_key``). Ids come
from one global atomic counter so the URL is a readable, globally ordered
number (``/chat/conversation/1``).

Access patterns:

* by id (owner)      GetItem on ``USER#<userId>`` / ``CHAT#<id>`` (strong)
* by user (sidebar)  Query GSI2 ``byUser`` on ``CHAT#`` prefix, newest first
* by agent (builder) Query GSI1 ``byId`` on ``CHATAGENT#<agentId>``, newest first
"""

from __future__ import annotations

from typing import Any

from data.client import now_iso, table
from data.keys import (
    CONV_COUNTER_PK,
    CONV_COUNTER_SK,
    GSI1,
    GSI2,
    chat_agent_pk,
    chat_agent_sk,
    chat_by_user_sk,
    chat_sk,
    user_pk,
)

KIND_CHAT = "chat"
KIND_RUN = "run"
KINDS = (KIND_CHAT, KIND_RUN)


def next_conversation_id() -> int:
    """Mint the next global conversation id (atomic ADD on the counter item)."""
    response = table().update_item(
        Key={"pk": CONV_COUNTER_PK, "sk": CONV_COUNTER_SK},
        UpdateExpression="ADD nextValue :one",
        ExpressionAttributeValues={":one": 1},
        ReturnValues="UPDATED_NEW",
    )
    return int(response["Attributes"]["nextValue"])


def _new_item(
    *,
    conversation_id: int,
    user_id: str,
    agent_id: str,
    agent_name: str,
    kind: str,
    title: str,
    created_at: str,
) -> dict[str, Any]:
    return {
        "pk": user_pk(user_id),
        "sk": chat_sk(conversation_id),
        "entity": "conversation",
        "conversationId": conversation_id,
        "userId": user_id,
        "agentId": agent_id,
        "agentName": agent_name,
        "kind": kind,
        "title": title,
        "lastPreview": "",
        "messageCount": 0,
        "runCount": 0,
        "createdAt": created_at,
        "updatedAt": created_at,
        "gsi1pk": chat_agent_pk(agent_id),
        "gsi1sk": chat_agent_sk(created_at, conversation_id),
        "gsi2pk": user_pk(user_id),
        "gsi2sk": chat_by_user_sk(created_at, conversation_id),
    }


def create_conversation(
    *,
    user_id: str,
    agent_id: str,
    agent_name: str,
    kind: str = KIND_CHAT,
    title: str = "",
) -> dict[str, Any]:
    conversation_id = next_conversation_id()
    item = _new_item(
        conversation_id=conversation_id,
        user_id=user_id,
        agent_id=agent_id,
        agent_name=agent_name,
        kind=kind,
        title=title,
        created_at=now_iso(),
    )
    table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    return item


def get_conversation(user_id: str, conversation_id: int) -> dict[str, Any] | None:
    response = table().get_item(
        Key={"pk": user_pk(user_id), "sk": chat_sk(conversation_id)}
    )
    return response.get("Item")


def list_conversations(
    user_id: str, limit: int = 50, start_key: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """A user's conversations, newest first (sidebar)."""
    kwargs: dict[str, Any] = {
        "IndexName": "byUser",
        "KeyConditionExpression": "gsi2pk = :pk AND begins_with(gsi2sk, :prefix)",
        "ExpressionAttributeValues": {":pk": user_pk(user_id), ":prefix": "CHAT#"},
        "ScanIndexForward": False,
        "Limit": limit,
    }
    if start_key:
        kwargs["ExclusiveStartKey"] = start_key
    response = table().query(**kwargs)
    return response.get("Items") or [], response.get("LastEvaluatedKey")


def list_conversations_for_agent(
    user_id: str,
    agent_id: str,
    limit: int = 50,
    start_key: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """One agent's conversations, newest first (builder history)."""
    kwargs: dict[str, Any] = {
        "IndexName": "byId",
        "KeyConditionExpression": "gsi1pk = :pk",
        "ExpressionAttributeValues": {":pk": chat_agent_pk(agent_id)},
        "ScanIndexForward": False,
        "Limit": limit,
    }
    if start_key:
        kwargs["ExclusiveStartKey"] = start_key
    response = table().query(**kwargs)
    return response.get("Items") or [], response.get("LastEvaluatedKey")


def update_conversation(
    user_id: str, conversation_id: int, *, title: str | None = None
) -> dict[str, Any] | None:
    """Rename a conversation (only field a user may edit directly)."""
    if title is None:
        return get_conversation(user_id, conversation_id)
    response = table().update_item(
        Key={"pk": user_pk(user_id), "sk": chat_sk(conversation_id)},
        UpdateExpression="SET #title = :title, updatedAt = :ts",
        ExpressionAttributeNames={"#title": "title"},
        ExpressionAttributeValues={":title": title, ":ts": now_iso()},
        ConditionExpression="attribute_exists(pk)",
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes")


def record_run(
    user_id: str,
    conversation_id: int,
    *,
    run_id: str,
    preview: str = "",
) -> None:
    """Bump counters + recency after a run (best-effort; called by the runtime)."""
    timestamp = now_iso()
    table().update_item(
        Key={"pk": user_pk(user_id), "sk": chat_sk(conversation_id)},
        UpdateExpression=(
            "SET updatedAt = :ts, lastRunId = :run, lastPreview = :preview, "
            "gsi1sk = :g1, gsi2sk = :g2 "
            "ADD messageCount :one, runCount :one"
        ),
        ExpressionAttributeValues={
            ":ts": timestamp,
            ":run": run_id,
            ":preview": preview[:280],
            ":g1": chat_agent_sk(timestamp, conversation_id),
            ":g2": chat_by_user_sk(timestamp, conversation_id),
            ":one": 1,
        },
        ConditionExpression="attribute_exists(pk)",
    )


def delete_conversation(user_id: str, conversation_id: int) -> dict[str, Any] | None:
    response = table().delete_item(
        Key={"pk": user_pk(user_id), "sk": chat_sk(conversation_id)},
        ReturnValues="ALL_OLD",
    )
    return response.get("Attributes")
