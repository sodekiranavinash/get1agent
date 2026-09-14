"""Shared MCP-over-Lambda transport for the get1agent MCP servers.

Each MCP server Lambda (``knowledge-mcp``, ``web-search``, ``code-interpreter``)
owns its own tools and uses this module to expose them over two transports:

* **HTTP (API Gateway):** the request body is a JSON-RPC message and the caller's
  identity comes from the JWT authorizer claims. ``authorize`` (default
  :func:`require_user`) gates the surface, and ``resolve_user_id`` maps the Auth0
  ``sub`` to the internal userId when the server stores user-scoped data.
* **Direct Lambda invoke:** the event is a JSON-RPC message plus ``userId``
  (already the internal id). Used by ``mcp-tester``; the caller's IAM role is the
  trust boundary.

The active user's internal id is stashed in a ContextVar for the request so tool
functions can read it with :func:`require_sub`.
"""

from __future__ import annotations

import json
import sys
import traceback
from contextvars import ContextVar
from typing import Any, Callable

from ai.auth import AuthError, require_user

_current_sub: ContextVar[str | None] = ContextVar("mcp_current_sub", default=None)


def current_sub() -> str | None:
    """The authenticated internal user id for the in-flight request, if any."""
    return _current_sub.get()


def require_sub() -> str:
    """Return the caller's internal user id or raise when there is no identity."""
    sub = _current_sub.get()
    if not sub:
        raise RuntimeError("No authenticated user in request context")
    return sub


def _claims(event: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]
    except (KeyError, TypeError, AttributeError):
        return None


def _claims_sub(event: dict[str, Any]) -> str | None:
    claims = _claims(event)
    if not claims:
        return None
    return str(claims.get("sub") or "").strip() or None


def _is_http_event(event: dict[str, Any]) -> bool:
    return "body" in event and ("requestContext" in event or "httpMethod" in event)


def _json_http_error(status_code: int, message: str) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"error": message}),
    }


def _error_response(code: int, message: str, request_id: Any = None) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
        ),
    }


def build_handler(
    mcp: Any,
    *,
    authorize: Callable[[dict[str, Any] | None, dict[str, Any]], None] = require_user,
    resolve_user_id: Callable[[str], str | None] | None = None,
) -> Callable[[dict[str, Any], Any], dict[str, Any]]:
    """Wrap an ``MCPLambdaHandler`` in the HTTP + direct-invoke transport.

    ``authorize`` is applied to HTTP requests only; direct invokes are trusted
    because only callers with ``lambda:InvokeFunction`` can reach them.

    ``resolve_user_id`` maps the JWT ``sub`` to the internal userId for HTTP
    requests. Servers that key user data (knowledge-mcp, code-interpreter) pass
    it; servers that only need an authenticated caller (web-search) leave it out.
    Direct invokes already carry the internal ``userId`` and are never resolved.
    """

    def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
        event = event if isinstance(event, dict) else {}

        if _is_http_event(event):
            try:
                authorize(_claims(event), event)
            except AuthError as exc:
                return _json_http_error(exc.status, exc.message)
            sub = _claims_sub(event)
            if resolve_user_id is not None and sub:
                sub = resolve_user_id(sub)
            _current_sub.set(sub)
            try:
                return mcp.handle_request(event, context)
            except Exception as exc:  # noqa: BLE001
                print(f"mcp server error: {exc!r}", file=sys.stderr)
                traceback.print_exc()
                return _error_response(-32603, "Internal error")

        # Direct Lambda invoke transport: a JSON-RPC message plus caller identity.
        user_id = event.get("userId")
        _current_sub.set(str(user_id).strip() if user_id else None)
        message = {
            key: event[key]
            for key in ("jsonrpc", "id", "method", "params")
            if key in event
        }
        message.setdefault("jsonrpc", "2.0")
        if "method" not in message:
            return {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32600, "message": "Invalid Request"},
            }

        try:
            response = mcp.handle_request(
                {
                    "headers": {"content-type": "application/json"},
                    "body": json.dumps(message),
                    "httpMethod": "POST",
                },
                context,
            )
            return json.loads(response.get("body") or "{}")
        except Exception as exc:  # noqa: BLE001
            print(f"mcp server direct error: {exc!r}", file=sys.stderr)
            traceback.print_exc()
            return {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32603, "message": "Internal error"},
            }

    return lambda_handler
