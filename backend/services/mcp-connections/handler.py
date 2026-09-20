"""Remote MCP connections API + aggregator.

Routes:

* ``GET    /v1/mcp/catalog``                       — curated public servers.
* ``GET    /v1/mcp/connections``                   — the user's connections.
* ``POST   /v1/mcp/connections``                   — start a connection (OAuth or none).
* ``GET    /v1/mcp/connections/{id}``              — one connection's status.
* ``DELETE /v1/mcp/connections/{id}``              — disconnect.
* ``POST   /v1/mcp/connections/{id}/refresh``      — force a token refresh.
* ``POST   /v1/mcp/connections/{id}/token``        — submit an API key.
* ``GET    /v1/mcp/connections/{id}/tools``        — list the remote tools.
* ``POST   /v1/mcp/connections/{id}/call``         — call one remote tool.
* ``GET    /v1/mcp/oauth/callback``                — OAuth redirect target (no JWT).
* ``POST   /mcp/remote``                           — aggregated MCP server for agents.

The callback is unauthenticated by design (it is a browser redirect): the
single-use ``state`` value is the credential, and it embeds the user id so no
Scan is needed to find the pending connection.
"""

from __future__ import annotations

import base64
import json
import sys
import traceback
from typing import Any
from urllib.parse import parse_qs

from core.auth import AuthError, require_user
from core.mcp_server import build_handler
from data.repositories.users import get_or_create_user, get_user_by_sub

from src import service
from src.aggregator import RemoteMCPHandler
from src.service import ApiError


def _json(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json", "cache-control": "no-store"},
        "body": json.dumps(body, default=str),
    }


def _no_content() -> dict[str, Any]:
    return {"statusCode": 204, "headers": {"cache-control": "no-store"}, "body": ""}


def _claims(event: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]
    except (KeyError, TypeError):
        return None


def _method(event: dict[str, Any]) -> str:
    method = event.get("requestContext", {}).get("http", {}).get(
        "method", event.get("httpMethod", "GET")
    )
    return str(method).upper()


def _path(event: dict[str, Any]) -> str:
    raw = event.get("rawPath") or event.get("path") or ""
    return raw.split("?", 1)[0].rstrip("/")


def _segments(event: dict[str, Any]) -> list[str]:
    return [segment for segment in _path(event).split("/") if segment]


def _body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body")
    if not raw:
        return {}
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ApiError(400, "Request body must be a JSON object")
    return parsed


def _query(event: dict[str, Any]) -> dict[str, str]:
    raw = event.get("rawQueryString") or ""
    if raw:
        parsed = parse_qs(raw)
        return {key: values[0] for key, values in parsed.items() if values}
    params = event.get("queryStringParameters") or {}
    return {key: str(value) for key, value in params.items() if value is not None}


def _resolve_user_id(sub: str | None) -> str | None:
    """Map an Auth0 ``sub`` to the internal userId (used by the MCP transport)."""
    sub = (sub or "").strip()
    if not sub:
        return None
    profile = get_user_by_sub(sub)
    if not profile:
        return None
    return str(profile.get("userId") or "").strip() or None


def _user_id_from_claims(claims: dict[str, Any]) -> str:
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise ApiError(401, "Unauthorized")
    profile = get_user_by_sub(sub) or get_or_create_user(claims)
    user_id = str((profile or {}).get("userId") or "").strip()
    if not user_id:
        raise ApiError(500, "Could not resolve the account")
    return user_id


# --- routing -----------------------------------------------------------------


def _route(
    user_id: str,
    method: str,
    segments: list[str],
    body: dict[str, Any],
    query: dict[str, str],
) -> dict[str, Any]:
    if segments[:2] != ["v1", "mcp"]:
        raise ApiError(404, "Not found")
    rest = segments[2:]

    if rest == ["catalog"]:
        if method == "GET":
            return _json(200, {"servers": service.public_catalog()})
        raise ApiError(405, f"Method not allowed: {method}")

    if rest == ["registry"]:
        if method == "GET":
            return _json(200, service.search_registry(query))
        raise ApiError(405, f"Method not allowed: {method}")

    if rest == ["connections"]:
        if method == "GET":
            return _json(200, {"connections": service.list_connections(user_id)})
        if method == "POST":
            return _json(201, service.start_connection(user_id, body))
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) >= 2 and rest[0] == "connections":
        conn_id = rest[1]
        if len(rest) == 2:
            if method == "GET":
                return _json(200, service.get_connection(user_id, conn_id))
            if method == "PATCH":
                return _json(200, service.set_enabled(user_id, conn_id, body.get("enabled")))
            if method == "DELETE":
                service.disconnect(user_id, conn_id)
                return _no_content()
            raise ApiError(405, f"Method not allowed: {method}")

        action = rest[2]
        if action == "refresh" and method == "POST":
            return _json(200, service.refresh_connection(user_id, conn_id))
        if action == "authorize" and method == "POST":
            return _json(200, service.reauthorize(user_id, conn_id))
        if action == "token" and method == "POST":
            token = str(body.get("token") or "").strip()
            return _json(200, service.set_api_key(user_id, conn_id, token))
        if action == "tools" and method == "GET":
            return _json(200, {"tools": service.list_tools_public(user_id, conn_id)})
        if action == "tools" and method == "PATCH":
            service.set_tool_enabled(
                user_id, conn_id, body.get("name"), body.get("enabled")
            )
            return _json(200, {"tools": service.list_tools_public(user_id, conn_id)})
        if action == "call" and method == "POST":
            name = str(body.get("name") or "").strip()
            if not name:
                raise ApiError(400, "name is required")
            arguments = body.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise ApiError(400, "arguments must be a JSON object")
            result = service.call_connection_tool(user_id, conn_id, name, arguments)
            return _json(200, {"result": result})
        raise ApiError(405, f"Method not allowed: {method}")

    raise ApiError(404, "Not found")


# Aggregated MCP server for agents (HTTP JWT + direct invoke).
_remote_mcp = build_handler(
    RemoteMCPHandler("get1agent-remote-mcp"), resolve_user_id=_resolve_user_id
)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    event = event if isinstance(event, dict) else {}
    path = _path(event)

    if path.endswith("/mcp/remote"):
        return _remote_mcp(event, context)

    if path.endswith("/v1/mcp/oauth/callback"):
        return service.handle_callback(_query(event))

    claims = _claims(event)
    if not claims:
        return _json(401, {"error": "Unauthorized"})
    try:
        require_user(claims, event)
    except AuthError as exc:
        return _json(exc.status, {"error": exc.message})

    try:
        user_id = _user_id_from_claims(claims)
        return _route(
            user_id, _method(event), _segments(event), _body(event), _query(event)
        )
    except ApiError as exc:
        return _json(exc.status, {"error": exc.message})
    except ValueError as exc:
        return _json(400, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        print(f"mcp-connections error: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        return _json(500, {"error": "Internal server error"})
