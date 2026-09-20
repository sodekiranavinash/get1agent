"""Agent repository.

An agent is a single item: its graph + settings live in the ``config`` map
(small metadata — prompt, model, references to KBs/skills/MCP servers, the
node/edge graph and an optional schedule). KBs/skills/servers are referenced by
id, never embedded.

Keys (single table, see design/design-b-dynamodb-s3.md Part 6):

    Agent           USER#<userId>    AGENT#<lowerName>
    GSI1 byId       AGENT#<agentId>  #META
    GSI2 byUser     USER#<userId>    AGENT#<updatedAt>#<name>
    GSI3 byStatus   AGENTLIB#public  <publishedAt>#<agentId>   (published only)

The public library is listed by querying the shared ``AGENTLIB#public`` GSI3
partition, so it never needs a Scan.
"""

from __future__ import annotations

from typing import Any

from data.client import now_iso, table
from data.keys import (
    AGENT_PREFIX,
    AGENT_PUBLIC_PK,
    GSI1,
    GSI2,
    GSI3,
    META,
    agent_public_sk,
    agent_sk,
    user_pk,
)


class DuplicateAgent(Exception):
    pass


def _new_item(
    sub: str,
    *,
    agent_id: str,
    name: str,
    description: str,
    config: dict[str, Any],
    status: str,
    visibility: str,
    source: str,
    version: int = 1,
    forked_from: str | None = None,
    verified_at: str | None = None,
    last_run_at: str | None = None,
    published_at: str | None = None,
    install_count: int = 0,
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = now_iso()
    graph = config.get("graph") or {}
    item: dict[str, Any] = {
        "pk": user_pk(sub),
        "sk": agent_sk(name),
        "entity": "agent",
        "agentId": agent_id,
        "userId": sub,
        "name": name,
        "description": description,
        "status": status,
        "visibility": visibility,
        "source": source,
        "version": version,
        "config": config,
        "nodeCount": len(graph.get("nodes") or []),
        "forkedFrom": forked_from,
        "installCount": install_count,
        "verifiedAt": verified_at,
        "lastRunAt": last_run_at,
        "publishedAt": published_at,
        "createdAt": created_at or timestamp,
        "updatedAt": timestamp,
        GSI1[0]: f"{AGENT_PREFIX}{agent_id}",
        GSI1[1]: META,
        GSI2[0]: user_pk(sub),
        GSI2[1]: f"{AGENT_PREFIX}{timestamp}#{name}",
    }
    if visibility == "public" and published_at:
        item[GSI3[0]] = AGENT_PUBLIC_PK
        item[GSI3[1]] = agent_public_sk(published_at, agent_id)
    return item


def create_agent(
    sub: str,
    *,
    agent_id: str,
    name: str,
    description: str,
    config: dict[str, Any],
    source: str = "write",
    forked_from: str | None = None,
) -> dict[str, Any]:
    item = _new_item(
        sub,
        agent_id=agent_id,
        name=name,
        description=description,
        config=config,
        status="draft",
        visibility="private",
        source=source,
        forked_from=forked_from,
    )
    try:
        table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    except Exception as exc:  # noqa: BLE001
        if _is_conditional_failure(exc):
            raise DuplicateAgent(name) from exc
        raise
    return item


def list_agents(sub: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "IndexName": "byUser",
        "KeyConditionExpression": f"{GSI2[0]} = :pk AND begins_with({GSI2[1]}, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": user_pk(sub),
            ":prefix": AGENT_PREFIX,
        },
        "ScanIndexForward": False,
    }
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return sorted(items, key=lambda item: item.get("name", ""))


def get_agent(sub: str, agent_id: str) -> dict[str, Any] | None:
    item = _get_by_id(agent_id)
    if item is None or item.get("userId") != sub:
        return None
    return item


def get_agent_by_name(sub: str, name: str) -> dict[str, Any] | None:
    response = table().get_item(Key={"pk": user_pk(sub), "sk": agent_sk(name)})
    return response.get("Item")


def get_public_agent(agent_id: str) -> dict[str, Any] | None:
    """Fetch a published agent regardless of owner (for library install)."""
    item = _get_by_id(agent_id)
    if item is None or item.get("visibility") != "public":
        return None
    return item


def update_agent(
    sub: str,
    agent_id: str,
    *,
    name: str,
    description: str,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """Full replace. Any edit resets verification and unpublishes the agent.

    The verified flag is a promise about an exact configuration, so changing the
    config invalidates it — the user must re-run the test to publish again.
    """
    existing = get_agent(sub, agent_id)
    if existing is None:
        return None
    new_item = _new_item(
        sub,
        agent_id=agent_id,
        name=name,
        description=description,
        config=config,
        status="draft",
        visibility="private",
        source=existing.get("source") or "write",
        version=int(existing.get("version") or 1) + 1,
        forked_from=existing.get("forkedFrom"),
        install_count=int(existing.get("installCount") or 0),
        created_at=existing.get("createdAt"),
    )
    if existing["sk"] == new_item["sk"]:
        # Same name: overwrite in place. The uniqueness condition only applies
        # when claiming a *new* name, so a plain re-save must not trip it.
        table().put_item(Item=new_item)
        return new_item

    # Renamed: claim the new key first (so a clash leaves the old item intact),
    # then drop the old key.
    try:
        table().put_item(Item=new_item, ConditionExpression="attribute_not_exists(pk)")
    except Exception as exc:  # noqa: BLE001
        if _is_conditional_failure(exc):
            raise DuplicateAgent(name) from exc
        raise
    table().delete_item(Key={"pk": existing["pk"], "sk": existing["sk"]})
    return new_item


def delete_agent(sub: str, agent_id: str) -> dict[str, Any] | None:
    existing = get_agent(sub, agent_id)
    if existing is None:
        return None
    table().delete_item(Key={"pk": existing["pk"], "sk": existing["sk"]})
    return existing


def count_agents(sub: str) -> int:
    response = table().query(
        IndexName="byUser",
        KeyConditionExpression=f"{GSI2[0]} = :pk AND begins_with({GSI2[1]}, :prefix)",
        ExpressionAttributeValues={
            ":pk": user_pk(sub),
            ":prefix": AGENT_PREFIX,
        },
        Select="COUNT",
    )
    return int(response.get("Count") or 0)


def mark_verified(sub: str, agent_id: str, *, status: str, verified_at: str) -> None:
    existing = get_agent(sub, agent_id)
    if existing is None:
        return
    table().update_item(
        Key={"pk": existing["pk"], "sk": existing["sk"]},
        UpdateExpression=(
            "SET #status = :status, verifiedAt = :verified, updatedAt = :updated"
        ),
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": status,
            ":verified": verified_at,
            ":updated": now_iso(),
        },
    )


def publish_agent(sub: str, agent_id: str, *, published_at: str) -> dict[str, Any] | None:
    existing = get_agent(sub, agent_id)
    if existing is None:
        return None
    table().update_item(
        Key={"pk": existing["pk"], "sk": existing["sk"]},
        UpdateExpression=(
            "SET #status = :status, visibility = :visibility, "
            "publishedAt = :published, updatedAt = :updated, "
            f"{GSI3[0]} = :gpk, {GSI3[1]} = :gsk"
        ),
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": "published",
            ":visibility": "public",
            ":published": published_at,
            ":updated": now_iso(),
            ":gpk": AGENT_PUBLIC_PK,
            ":gsk": agent_public_sk(published_at, agent_id),
        },
    )
    return get_agent(sub, agent_id)


def unpublish_agent(sub: str, agent_id: str) -> dict[str, Any] | None:
    existing = get_agent(sub, agent_id)
    if existing is None:
        return None
    table().update_item(
        Key={"pk": existing["pk"], "sk": existing["sk"]},
        UpdateExpression=(
            "SET #status = :status, visibility = :visibility, updatedAt = :updated "
            f"REMOVE publishedAt, {GSI3[0]}, {GSI3[1]}"
        ),
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": "verified",
            ":visibility": "private",
            ":updated": now_iso(),
        },
    )
    return get_agent(sub, agent_id)


def list_library(
    *, limit: int = 60, exclusive_start_key: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    kwargs: dict[str, Any] = {
        "IndexName": "byStatus",
        "KeyConditionExpression": f"{GSI3[0]} = :pk",
        "ExpressionAttributeValues": {":pk": AGENT_PUBLIC_PK},
        "ScanIndexForward": False,
        "Limit": limit,
    }
    if exclusive_start_key:
        kwargs["ExclusiveStartKey"] = exclusive_start_key
    response = table().query(**kwargs)
    return list(response.get("Items") or []), response.get("LastEvaluatedKey")


def adjust_install_count(item: dict[str, Any], delta: int = 1) -> None:
    """Best-effort counter bump on a published agent (its own item)."""
    try:
        table().update_item(
            Key={"pk": item["pk"], "sk": item["sk"]},
            UpdateExpression="ADD installCount :delta",
            ExpressionAttributeValues={":delta": delta},
        )
    except Exception:  # noqa: BLE001 - never fail an install on a counter bump
        pass


def _get_by_id(agent_id: str) -> dict[str, Any] | None:
    response = table().query(
        IndexName="byId",
        KeyConditionExpression=f"{GSI1[0]} = :pk",
        ExpressionAttributeValues={":pk": f"{AGENT_PREFIX}{agent_id}"},
        Limit=1,
    )
    items = response.get("Items") or []
    return items[0] if items else None


def _is_conditional_failure(exc: BaseException) -> bool:
    from botocore.exceptions import ClientError

    return (
        isinstance(exc, ClientError)
        and exc.response.get("Error", {}).get("Code")
        == "ConditionalCheckFailedException"
    )
