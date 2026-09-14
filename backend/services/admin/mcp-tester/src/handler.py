"""Admin MCP tester Lambda.

A thin, admin-only proxy that lets the admin UI exercise the tools exposed by
the get1agent MCP servers (``knowledge-mcp``, ``web-search``,
``code-interpreter``). It is the MCP *client*: it reads the caller's admin claim
and ``sub`` from the JWT, builds standard MCP JSON-RPC messages, and invokes the
servers over their direct-invoke transport.

Routes (JWT-protected, admin-only):

* ``GET  /v1/admin/mcp/tools`` — MCP ``tools/list`` across every server.
* ``POST /v1/admin/mcp/call``  — MCP ``tools/call`` routed to the owning server.

Every response includes the exact JSON-RPC ``request``/``response`` and the
duration so the admin can inspect exactly what happened.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from typing import Any

from ai.auth import AuthError, require_admin
from ai.mcp_client import (
    McpClientError,
    call_tool,
    find_tool_server,
    list_tools_multi,
)
from shared.users import get_or_create_user, get_user_by_sub


def _json(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json", "cache-control": "no-store"},
        "body": json.dumps(body, default=str),
    }


def _mcp_functions() -> list[str]:
    raw = os.environ.get("MCP_FUNCTIONS") or os.environ.get("MCP_FUNCTION") or ""
    return [name.strip() for name in raw.split(",") if name.strip()]


def _claims(event: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]
    except (KeyError, TypeError):
        return None


def _resolve_user(claims: dict[str, Any], sub: str) -> dict[str, Any]:
    """Resolve the caller's profile (creating it if needed) for identity + display."""
    if not sub:
        return {}
    try:
        profile = get_user_by_sub(sub)
        if not profile:
            profile = get_or_create_user(claims)
        return profile
    except Exception as exc:  # noqa: BLE001
        print(f"mcp-tester user lookup failed: {exc!r}", file=sys.stderr)
        return {}


def _method(event: dict[str, Any]) -> str:
    method = event.get("requestContext", {}).get("http", {}).get(
        "method", event.get("httpMethod", "GET")
    )
    return str(method).upper()


def _path(event: dict[str, Any]) -> str:
    raw = event.get("rawPath") or event.get("path") or ""
    return raw.split("?", 1)[0].rstrip("/")


def _body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body")
    if not raw:
        return {}
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Request body must be a JSON object")
    return parsed


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _text_payload(response: dict[str, Any]) -> Any:
    """Parse the JSON string carried in the first MCP text content block."""
    try:
        blocks = response["result"]["content"]
    except (KeyError, TypeError):
        return None
    if not isinstance(blocks, list):
        return None
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                try:
                    return json.loads(text)
                except ValueError:
                    return None
    return None


def _handle_list_tools(
    functions: list[str], user_id: str, region: str | None
) -> dict[str, Any]:
    started = time.perf_counter()
    tools, per_server = list_tools_multi(functions, user_id, region)
    duration = _elapsed_ms(started)
    return _json(
        200,
        {
            "ok": True,
            "tools": tools,
            "servers": per_server,
            "userId": user_id,
            "durationMs": duration,
        },
    )


def _handle_call_tool(
    functions: list[str],
    user_id: str,
    region: str | None,
    body: dict[str, Any],
) -> dict[str, Any]:
    name = str(body.get("name") or "").strip()
    if not name:
        return _json(400, {"error": "name is required"})
    arguments = body.get("arguments")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return _json(400, {"error": "arguments must be a JSON object"})

    started = time.perf_counter()
    server = find_tool_server(functions, user_id, name, region)
    if not server:
        return _json(
            200,
            {
                "ok": False,
                "tool": name,
                "userId": user_id,
                "arguments": arguments,
                "error": {"code": -32601, "message": f"Tool '{name}' not found"},
                "request": None,
                "response": None,
                "durationMs": _elapsed_ms(started),
            },
        )

    request, response = call_tool(server, user_id, name, arguments, region)
    duration = _elapsed_ms(started)

    if "error" in response:
        return _json(
            200,
            {
                "ok": False,
                "tool": name,
                "server": server,
                "userId": user_id,
                "arguments": arguments,
                "error": response["error"],
                "request": request,
                "response": response,
                "durationMs": duration,
            },
        )

    return _json(
        200,
        {
            "ok": True,
            "tool": name,
            "server": server,
            "userId": user_id,
            "arguments": arguments,
            "result": response.get("result"),
            "data": _text_payload(response),
            "request": request,
            "response": response,
            "durationMs": duration,
        },
    )


def lambda_handler(event: dict[str, Any], _context) -> dict[str, Any]:
    event = event if isinstance(event, dict) else {}

    claims = _claims(event)
    if not claims:
        return _json(401, {"error": "Unauthorized"})
    try:
        require_admin(claims, event)
    except AuthError as exc:
        return _json(exc.status, {"error": exc.message})

    functions = _mcp_functions()
    if not functions:
        return _json(500, {"error": "MCP_FUNCTIONS is not configured"})
    region = os.environ.get("AWS_REGION")
    sub = str(claims.get("sub") or "").strip()
    profile = _resolve_user(claims, sub)
    user_id = str(profile.get("userId") or sub).strip()

    method = _method(event)
    path = _path(event)

    try:
        if method == "GET" and path.endswith("/mcp/tools"):
            return _handle_list_tools(functions, user_id, region)
        if method == "POST" and path.endswith("/mcp/call"):
            return _handle_call_tool(functions, user_id, region, _body(event))
        return _json(404, {"error": "Not found"})
    except (McpClientError, ValueError) as exc:
        return _json(502, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        print(f"mcp-tester error: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        return _json(500, {"error": "Internal server error"})
