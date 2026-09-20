"""Per-user connections to remote MCP servers.

One item per connection (``USER#<userId>`` / ``MCPCONN#<connId>``) plus a
short-lived, single-use OAuth state item (``MCPSTATE#<state>``, TTL). OAuth
credentials are stored **encrypted** (see ``core.crypto``) — this module only
moves opaque ciphertext strings around.

Rotation-safe writes: ``save_tokens`` can require the refresh token it is
replacing to still be the stored one, so two concurrent refreshes cannot lose a
rotated token (the loser re-reads and reuses the winner's token).
"""

from __future__ import annotations

from typing import Any

from data.client import is_conditional_failure, now_epoch, now_iso, table
from data.keys import (
    MCPCONN_PREFIX,
    MCPSTATE_PREFIX,
    mcp_conn_sk,
    mcp_state_sk,
    user_pk,
)

# Connection lifecycle.
STATUS_PENDING = "pending"
STATUS_CONNECTED = "connected"
STATUS_REAUTH_REQUIRED = "reauth_required"
STATUS_ERROR = "error"

# In-flight OAuth state lives for 10 minutes.
MCP_STATE_TTL_SECONDS = 600

# Sentinel: caller did not ask for an optimistic-concurrency check.
_UNSET: Any = object()
# Public alias so callers can pass the sentinel explicitly.
UNSET = _UNSET


class ConnectionNotFound(Exception):
    pass


class RefreshConflict(Exception):
    """A concurrent refresh replaced the token we were rotating from."""


def _connection_item(
    user_id: str,
    conn_id: str,
    *,
    name: str,
    server_url: str,
    auth_type: str,
    description: str | None = None,
    transport: str = "streamable-http",
    catalog_id: str | None = None,
    status: str = STATUS_PENDING,
    scopes: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = created_at or now_iso()
    return {
        "pk": user_pk(user_id),
        "sk": mcp_conn_sk(conn_id),
        "entity": "mcp_connection",
        "connId": conn_id,
        "userId": user_id,
        "name": name,
        "description": description,
        "serverUrl": server_url,
        "transport": transport,
        "authType": auth_type,
        "catalogId": catalog_id,
        "scopes": list(scopes or []),
        "status": status,
        "enabled": True,
        "disabledTools": [],
        "toolCount": 0,
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }


def create_connection(
    user_id: str,
    conn_id: str,
    *,
    name: str,
    server_url: str,
    auth_type: str,
    description: str | None = None,
    transport: str = "streamable-http",
    catalog_id: str | None = None,
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    item = _connection_item(
        user_id,
        conn_id,
        name=name,
        server_url=server_url,
        auth_type=auth_type,
        description=description,
        transport=transport,
        catalog_id=catalog_id,
        scopes=scopes,
    )
    table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    return item


def get_connection(user_id: str, conn_id: str) -> dict[str, Any] | None:
    response = table().get_item(Key={"pk": user_pk(user_id), "sk": mcp_conn_sk(conn_id)})
    return response.get("Item")


def list_connections(user_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": user_pk(user_id),
            ":prefix": MCPCONN_PREFIX,
        },
    }
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return sorted(items, key=lambda item: item.get("name", "").lower())


def delete_connection(user_id: str, conn_id: str) -> dict[str, Any] | None:
    response = table().delete_item(
        Key={"pk": user_pk(user_id), "sk": mcp_conn_sk(conn_id)},
        ReturnValues="ALL_OLD",
    )
    return response.get("Attributes")


def update_connection(user_id: str, conn_id: str, **fields: Any) -> None:
    """Patch arbitrary metadata attributes (never raw token fields)."""
    if not fields:
        return
    sets: list[str] = []
    names: dict[str, str] = {}
    values: dict[str, Any] = {}
    for index, (key, value) in enumerate(fields.items()):
        name_token = f"#f{index}"
        value_token = f":v{index}"
        names[name_token] = key
        values[value_token] = value
        sets.append(f"{name_token} = {value_token}")
    names["#updatedAt"] = "updatedAt"
    values[":updatedAt"] = now_iso()
    sets.append("#updatedAt = :updatedAt")
    try:
        table().update_item(
            Key={"pk": user_pk(user_id), "sk": mcp_conn_sk(conn_id)},
            UpdateExpression="SET " + ", ".join(sets),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(pk)",
        )
    except Exception as exc:  # noqa: BLE001
        if is_conditional_failure(exc):
            raise ConnectionNotFound(conn_id) from exc
        raise


def set_enabled(user_id: str, conn_id: str, enabled: bool) -> None:
    """Toggle whether a connection's tools are exposed to agents."""
    update_connection(user_id, conn_id, enabled=bool(enabled))


def set_tool_enabled(user_id: str, conn_id: str, tool_name: str, enabled: bool) -> None:
    """Toggle a single tool within a connection.

    The disabled set is stored on the connection item (small metadata) so the
    aggregator and the skill editor can filter without calling the server.
    """
    connection = get_connection(user_id, conn_id)
    if connection is None:
        raise ConnectionNotFound(conn_id)
    disabled = [str(name) for name in connection.get("disabledTools") or []]
    if enabled:
        disabled = [name for name in disabled if name != tool_name]
    elif tool_name not in disabled:
        disabled.append(tool_name)
    update_connection(user_id, conn_id, disabledTools=disabled)


def set_status(
    user_id: str,
    conn_id: str,
    status: str,
    *,
    error: str | None = None,
    tool_count: int | None = None,
) -> None:
    sets = ["#status = :status", "#updatedAt = :updatedAt"]
    removes: list[str] = []
    names: dict[str, str] = {"#status": "status", "#updatedAt": "updatedAt"}
    values: dict[str, Any] = {":status": status, ":updatedAt": now_iso()}
    if error is not None:
        names["#lastError"] = "lastError"
        values[":lastError"] = error
        sets.append("#lastError = :lastError")
    elif status not in (STATUS_ERROR, STATUS_REAUTH_REQUIRED):
        # A successful reconnect clears any stale failure message.
        names["#lastError"] = "lastError"
        removes.append("#lastError")
    if tool_count is not None:
        names["#toolCount"] = "toolCount"
        values[":toolCount"] = int(tool_count)
        sets.append("#toolCount = :toolCount")

    expression = "SET " + ", ".join(sets)
    if removes:
        expression += " REMOVE " + ", ".join(removes)
    try:
        table().update_item(
            Key={"pk": user_pk(user_id), "sk": mcp_conn_sk(conn_id)},
            UpdateExpression=expression,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(pk)",
        )
    except Exception as exc:  # noqa: BLE001
        if is_conditional_failure(exc):
            raise ConnectionNotFound(conn_id) from exc
        raise


def save_tokens(
    user_id: str,
    conn_id: str,
    *,
    access_token_enc: str,
    refresh_token_enc: str | None = None,
    token_type: str = "Bearer",
    token_expires_at: int | None = None,
    expected_refresh_enc: Any = _UNSET,
) -> None:
    """Persist (possibly rotated) tokens.

    When ``expected_refresh_enc`` is supplied the write only succeeds if the
    stored refresh token still matches — the optimistic-concurrency guard that
    makes refresh-token rotation safe under concurrent tool calls.
    """
    sets = [
        "#access = :access",
        "#tokenType = :tokenType",
        "#status = :status",
        "#updatedAt = :updatedAt",
    ]
    names = {
        "#access": "accessTokenEnc",
        "#tokenType": "tokenType",
        "#status": "status",
        "#updatedAt": "updatedAt",
    }
    values: dict[str, Any] = {
        ":access": access_token_enc,
        ":tokenType": token_type,
        ":status": STATUS_CONNECTED,
        ":updatedAt": now_iso(),
        ":lastRefreshedAt": now_iso(),
    }
    sets.append("#lastRefreshedAt = :lastRefreshedAt")
    names["#lastRefreshedAt"] = "lastRefreshedAt"

    if token_expires_at is not None:
        sets.append("#expires = :expires")
        names["#expires"] = "tokenExpiresAt"
        values[":expires"] = int(token_expires_at)
    if refresh_token_enc is not None:
        sets.append("#refresh = :refresh")
        names["#refresh"] = "refreshTokenEnc"
        values[":refresh"] = refresh_token_enc

    kwargs: dict[str, Any] = {
        "Key": {"pk": user_pk(user_id), "sk": mcp_conn_sk(conn_id)},
        "UpdateExpression": "SET " + ", ".join(sets),
        "ExpressionAttributeNames": names,
        "ExpressionAttributeValues": values,
    }
    if expected_refresh_enc is not _UNSET:
        kwargs["ConditionExpression"] = "#refresh = :expected"
        names.setdefault("#refresh", "refreshTokenEnc")
        values[":expected"] = expected_refresh_enc

    try:
        table().update_item(**kwargs)
    except Exception as exc:  # noqa: BLE001
        if is_conditional_failure(exc):
            raise RefreshConflict(conn_id) from exc
        raise


def save_client(
    user_id: str,
    conn_id: str,
    *,
    client_id: str,
    client_secret_enc: str | None,
    issuer: str | None,
    authorization_server: str | None,
    authorization_endpoint: str | None,
    token_endpoint: str | None,
    resource: str | None,
    registration_method: str,
) -> None:
    fields: dict[str, Any] = {
        "clientId": client_id,
        "issuer": issuer,
        "authorizationServer": authorization_server,
        "authorizationEndpoint": authorization_endpoint,
        "tokenEndpoint": token_endpoint,
        "resource": resource,
        "registrationMethod": registration_method,
    }
    if client_secret_enc is not None:
        fields["clientSecretEnc"] = client_secret_enc
    update_connection(user_id, conn_id, **fields)


# --- in-flight OAuth state ---------------------------------------------------


def create_state(user_id: str, state: str, **payload: Any) -> None:
    item = {
        "pk": user_pk(user_id),
        "sk": mcp_state_sk(state),
        "entity": "mcp_oauth_state",
        "state": state,
        "userId": user_id,
        "expiresAt": now_epoch() + MCP_STATE_TTL_SECONDS,
        **payload,
    }
    table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")


def consume_state(user_id: str, state: str) -> dict[str, Any] | None:
    """Atomically read-and-delete the state item, making it single-use."""
    response = table().delete_item(
        Key={"pk": user_pk(user_id), "sk": mcp_state_sk(state)},
        ReturnValues="ALL_OLD",
    )
    return response.get("Attributes")


def count_connections(user_id: str) -> int:
    response = table().query(
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={
            ":pk": user_pk(user_id),
            ":prefix": MCPCONN_PREFIX,
        },
        Select="COUNT",
    )
    return int(response.get("Count") or 0)
