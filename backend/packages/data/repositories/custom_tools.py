"""User-defined MCP servers and their Python tools.

One small item per server (``USER#<userId>`` / ``CSERVER#<slug>``) and one per
tool (``USER#<userId>`` / ``CTOOL#<slug>#<name>``). Tool metadata and the JSON
schemas live in DynamoDB; the tool source lives in S3
(``retrieval.layout.custom_tool_key``). This keeps items tiny and the bulky
code out of the table.
"""

from __future__ import annotations

from typing import Any

from data.client import now_iso, table
from data.keys import (
    CSERVER_PREFIX,
    CTOOL_PREFIX,
    GSI1,
    META,
    custom_server_sk,
    custom_tool_sk,
    user_pk,
)


class DuplicateCustomServer(Exception):
    pass


class DuplicateCustomTool(Exception):
    pass


def slugify(value: str) -> str:
    """Lowercase-hyphen slug used for a server's key and tool namespace."""
    import re

    slug = re.sub(r"[^a-z0-9-]+", "-", (value or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)[:48].strip("-")


def _is_conditional_failure(exc: BaseException) -> bool:
    from botocore.exceptions import ClientError

    return (
        isinstance(exc, ClientError)
        and exc.response.get("Error", {}).get("Code")
        == "ConditionalCheckFailedException"
    )


# --- servers -----------------------------------------------------------------


def _server_item(
    sub: str,
    *,
    server_id: str,
    name: str,
    slug: str,
    description: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "pk": user_pk(sub),
        "sk": custom_server_sk(slug),
        "entity": "customServer",
        "serverId": server_id,
        "userId": sub,
        "name": name,
        "slug": slug,
        "description": description,
        "toolCount": 0,
        "status": "active",
        "createdAt": created_at or timestamp,
        "updatedAt": timestamp,
        GSI1[0]: f"{CSERVER_PREFIX}{server_id}",
        GSI1[1]: META,
    }


def create_server(
    sub: str,
    *,
    server_id: str,
    name: str,
    slug: str,
    description: str,
) -> dict[str, Any]:
    item = _server_item(
        sub, server_id=server_id, name=name, slug=slug, description=description
    )
    try:
        table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    except Exception as exc:  # noqa: BLE001
        if _is_conditional_failure(exc):
            raise DuplicateCustomServer(name) from exc
        raise
    return item


def list_servers(sub: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": {":pk": user_pk(sub), ":prefix": CSERVER_PREFIX},
        "ScanIndexForward": True,
    }
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


def get_server(sub: str, server_id: str) -> dict[str, Any] | None:
    response = table().query(
        IndexName="byId",
        KeyConditionExpression=f"{GSI1[0]} = :pk",
        ExpressionAttributeValues={":pk": f"{CSERVER_PREFIX}{server_id}"},
        Limit=1,
    )
    items = response.get("Items") or []
    if not items:
        return None
    item = items[0]
    if item.get("userId") != sub:
        return None
    return item


def get_server_by_slug(sub: str, slug: str) -> dict[str, Any] | None:
    response = table().get_item(
        Key={"pk": user_pk(sub), "sk": custom_server_sk(slug)}
    )
    return response.get("Item")


def update_server(
    sub: str,
    server_id: str,
    *,
    name: str,
    slug: str,
    description: str,
) -> dict[str, Any] | None:
    existing = get_server(sub, server_id)
    if existing is None:
        return None
    new_item = _server_item(
        sub,
        server_id=server_id,
        name=name,
        slug=slug,
        description=description,
        created_at=existing.get("createdAt"),
    )
    new_item["toolCount"] = int(existing.get("toolCount") or 0)
    if existing["sk"] != new_item["sk"]:
        # Renaming moves the item; guard against colliding with an existing name.
        table().delete_item(Key={"pk": existing["pk"], "sk": existing["sk"]})
        try:
            table().put_item(
                Item=new_item, ConditionExpression="attribute_not_exists(pk)"
            )
        except Exception as exc:  # noqa: BLE001
            if _is_conditional_failure(exc):
                raise DuplicateCustomServer(name) from exc
            raise
    else:
        table().put_item(Item=new_item)
    return new_item


def delete_server(sub: str, server_id: str) -> dict[str, Any] | None:
    existing = get_server(sub, server_id)
    if existing is None:
        return None
    slug = str(existing.get("slug") or "")
    for tool in list_tools(sub, slug):
        table().delete_item(Key={"pk": tool["pk"], "sk": tool["sk"]})
    table().delete_item(Key={"pk": existing["pk"], "sk": existing["sk"]})
    return existing


def count_servers(sub: str) -> int:
    response = table().query(
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={":pk": user_pk(sub), ":prefix": CSERVER_PREFIX},
        Select="COUNT",
    )
    return int(response.get("Count") or 0)


def adjust_tool_count(sub: str, slug: str, delta: int) -> None:
    """Atomically nudge a server's tool count (best effort)."""
    try:
        table().update_item(
            Key={"pk": user_pk(sub), "sk": custom_server_sk(slug)},
            UpdateExpression="ADD toolCount :delta",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeValues={":delta": int(delta)},
        )
    except Exception:  # noqa: BLE001 - a stale count must not fail the request
        pass


# --- tools -------------------------------------------------------------------


def _tool_item(
    sub: str,
    *,
    tool_id: str,
    server_id: str,
    server_slug: str,
    name: str,
    description: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    code_key: str,
    code_hash: str,
    entrypoint: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "pk": user_pk(sub),
        "sk": custom_tool_sk(server_slug, name),
        "entity": "customTool",
        "toolId": tool_id,
        "serverId": server_id,
        "serverSlug": server_slug,
        "userId": sub,
        "name": name,
        "description": description,
        "inputSchema": input_schema,
        "outputSchema": output_schema,
        "codeKey": code_key,
        "codeHash": code_hash,
        "entrypoint": entrypoint,
        "createdAt": created_at or timestamp,
        "updatedAt": timestamp,
        GSI1[0]: f"{CTOOL_PREFIX}{tool_id}",
        GSI1[1]: META,
    }


def create_tool(
    sub: str,
    *,
    tool_id: str,
    server_id: str,
    server_slug: str,
    name: str,
    description: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    code_key: str,
    code_hash: str,
    entrypoint: str = "run",
) -> dict[str, Any]:
    item = _tool_item(
        sub,
        tool_id=tool_id,
        server_id=server_id,
        server_slug=server_slug,
        name=name,
        description=description,
        input_schema=input_schema,
        output_schema=output_schema,
        code_key=code_key,
        code_hash=code_hash,
        entrypoint=entrypoint,
    )
    try:
        table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    except Exception as exc:  # noqa: BLE001
        if _is_conditional_failure(exc):
            raise DuplicateCustomTool(name) from exc
        raise
    adjust_tool_count(sub, server_slug, 1)
    return item


def update_tool(
    sub: str,
    tool_id: str,
    *,
    server_id: str,
    server_slug: str,
    name: str,
    description: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    code_key: str,
    code_hash: str,
    entrypoint: str = "run",
) -> dict[str, Any] | None:
    existing = get_tool(sub, tool_id)
    if existing is None:
        return None
    new_item = _tool_item(
        sub,
        tool_id=tool_id,
        server_id=server_id,
        server_slug=server_slug,
        name=name,
        description=description,
        input_schema=input_schema,
        output_schema=output_schema,
        code_key=code_key,
        code_hash=code_hash,
        entrypoint=entrypoint,
        created_at=existing.get("createdAt"),
    )
    renamed = existing["sk"] != new_item["sk"]
    if renamed:
        # Renaming moves the item; guard against colliding with an existing name.
        table().delete_item(Key={"pk": existing["pk"], "sk": existing["sk"]})
        try:
            table().put_item(
                Item=new_item, ConditionExpression="attribute_not_exists(pk)"
            )
        except Exception as exc:  # noqa: BLE001
            if _is_conditional_failure(exc):
                raise DuplicateCustomTool(name) from exc
            raise
    else:
        table().put_item(Item=new_item)
    if renamed:
        adjust_tool_count(sub, str(existing.get("serverSlug") or ""), -1)
        adjust_tool_count(sub, server_slug, 1)
    return new_item


def list_tools(sub: str, server_slug: str) -> list[dict[str, Any]]:
    prefix = f"{CTOOL_PREFIX}{server_slug.lower()}#"
    return _query_tools(sub, prefix)


def list_all_tools(sub: str) -> list[dict[str, Any]]:
    return _query_tools(sub, CTOOL_PREFIX)


def _query_tools(sub: str, prefix: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": {":pk": user_pk(sub), ":prefix": prefix},
        "ScanIndexForward": True,
    }
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


def get_tool(sub: str, tool_id: str) -> dict[str, Any] | None:
    response = table().query(
        IndexName="byId",
        KeyConditionExpression=f"{GSI1[0]} = :pk",
        ExpressionAttributeValues={":pk": f"{CTOOL_PREFIX}{tool_id}"},
        Limit=1,
    )
    items = response.get("Items") or []
    if not items:
        return None
    item = items[0]
    if item.get("userId") != sub:
        return None
    return item


def get_tool_by_name(
    sub: str, server_slug: str, name: str
) -> dict[str, Any] | None:
    response = table().get_item(
        Key={"pk": user_pk(sub), "sk": custom_tool_sk(server_slug, name)}
    )
    return response.get("Item")


def delete_tool(sub: str, tool_id: str) -> dict[str, Any] | None:
    existing = get_tool(sub, tool_id)
    if existing is None:
        return None
    table().delete_item(Key={"pk": existing["pk"], "sk": existing["sk"]})
    adjust_tool_count(sub, str(existing.get("serverSlug") or ""), -1)
    return existing


def count_tools(sub: str) -> int:
    response = table().query(
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={":pk": user_pk(sub), ":prefix": CTOOL_PREFIX},
        Select="COUNT",
    )
    return int(response.get("Count") or 0)
