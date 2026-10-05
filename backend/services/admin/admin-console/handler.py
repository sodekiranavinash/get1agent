"""Admin console Lambda.

The admin-only API behind the admin console. It has three jobs:

* **MCP client** — exercise the tools exposed by the get1agent MCP servers
  (``knowledge-mcp``, ``web-search``, ``code-interpreter``): read the caller's
  admin claim and ``sub`` from the JWT, build standard MCP JSON-RPC messages and
  invoke the servers over direct-invoke Lambda transport or the AgentCore
  Gateway (``MCP_TRANSPORT``).
* **Admin operations** — AI-credit management and the support/security inboxes.
* **Platform status** — AgentCore Identity, Registry, Browser and Optimization
  plus the Bedrock cost/latency levers, under ``/v1/admin/platform/*``.

Routes (JWT-protected, admin-only):

* ``GET  /v1/admin/mcp/tools`` — MCP ``tools/list`` across every server.
* ``POST /v1/admin/mcp/call``  — MCP ``tools/call`` routed to the owning server.
* ``GET/POST /v1/admin/users…`` — AI credits.
* ``GET/POST /v1/admin/support…`` / ``/v1/admin/security-reports…`` — inboxes.
* ``GET/POST /v1/admin/platform/{identity,registry,browser}`` +
  ``GET /v1/admin/platform/{optimization,bedrock-features}`` — platform status.

MCP responses include the exact JSON-RPC ``request``/``response`` and the
duration so the admin can inspect exactly what happened.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from typing import Any

from core import usage as core_usage
from core.auth import AuthError, require_admin
from core.mcp_client import (
    McpClientError,
    call_tool,
    gateway_call_tool,
    gateway_list_tools,
    find_tool_server,
    list_tools_multi,
)
from data.repositories import quotas
from data.repositories import support as support_repo
from data.repositories.users import get_or_create_user, get_user_by_sub, list_users


def _json(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json", "cache-control": "no-store"},
        "body": json.dumps(body, default=str),
    }


def _mcp_functions() -> list[str]:
    raw = os.environ.get("MCP_FUNCTIONS") or os.environ.get("MCP_FUNCTION") or ""
    return [name.strip() for name in raw.split(",") if name.strip()]

def _mcp_transport() -> str:
    """Return 'gateway' if MCP_TRANSPORT=gateway and gateway URL is configured."""
    transport = (os.environ.get("MCP_TRANSPORT") or "aggregator").strip().lower()
    if transport == "gateway" and not os.environ.get("MCP_GATEWAY_URL"):
        # Gateway transport requires a gateway URL
        return "aggregator"
    return transport

def _gateway_url() -> str | None:
    """Return the MCP gateway URL if configured."""
    url = os.environ.get("MCP_GATEWAY_URL") or ""
    return url.strip() or None


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
        print(f"admin-console user lookup failed: {exc!r}", file=sys.stderr)
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
    functions: list[str], user_id: str, region: str | None,
    transport: str = "aggregator", gateway_url: str | None = None, session_id: str = ""
) -> dict[str, Any]:
    started = time.perf_counter()
    
    if transport == "gateway" and gateway_url:
        # Gateway mode: get tools from gateway
        try:
            response = gateway_list_tools(gateway_url, session_id, region)
        except McpClientError as exc:
            return _json(502, {"error": f"Gateway list tools failed: {exc}"})
        
        tools = []
        per_server = []
        
        # Parse gateway response
        result = response.get("result") or {}
        gateway_tools = result.get("tools") or []
        
        # Extract server info from gateway tool names (format: server___tool-name)
        for tool_spec in gateway_tools:
            if not isinstance(tool_spec, dict):
                continue
            tool_name = str(tool_spec.get("name") or "")
            if "___" in tool_name:
                server, base_tool_name = tool_name.split("___", 1)
            else:
                server = "gateway"
                base_tool_name = tool_name
            
            # Create normalized tool spec
            tool = {
                "name": base_tool_name,
                "description": tool_spec.get("description"),
                "inputSchema": tool_spec.get("inputSchema"),
                "server": server,
                "gateway_name": tool_name  # Keep original gateway name for calls
            }
            tools.append(tool)
        
        duration = _elapsed_ms(started)
        return _json(
            200,
            {
                "ok": True,
                "tools": tools,
                "servers": [{"function": "gateway", "request": {"method": "tools/list"}, "response": response}],
                "userId": user_id,
                "gatewayMode": True,
                "durationMs": duration,
            },
        )
    else:
        # Direct-invoke (aggregator) mode
        tools, per_server = list_tools_multi(functions, user_id, region)
        duration = _elapsed_ms(started)
        return _json(
            200,
            {
                "ok": True,
                "tools": tools,
                "servers": per_server,
                "userId": user_id,
                "gatewayMode": False,
                "durationMs": duration,
            },
        )


def _handle_call_tool(
    functions: list[str],
    user_id: str,
    region: str | None,
    body: dict[str, Any],
    transport: str = "aggregator",
    gateway_url: str | None = None,
    session_id: str = "",
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
    
    if transport == "gateway" and gateway_url:
        # Gateway mode
        # In gateway mode, we need to find the gateway tool name.
        # First, get the tool list to find the gateway name
        try:
            list_response = gateway_list_tools(gateway_url, session_id, region)
        except McpClientError as exc:
            return _json(502, {"error": f"Gateway list tools failed: {exc}"})
        
        # Find the gateway tool name
        result = list_response.get("result") or {}
        gateway_tools = result.get("tools") or []
        gateway_tool_name = None
        server_from_gateway = "gateway"
        
        for tool_spec in gateway_tools:
            if not isinstance(tool_spec, dict):
                continue
            tool_gateway_name = str(tool_spec.get("name") or "")
            # Check if this gateway tool matches the requested tool
            if "___" in tool_gateway_name:
                server_part, base_tool_name = tool_gateway_name.split("___", 1)
                if base_tool_name == name:
                    gateway_tool_name = tool_gateway_name
                    server_from_gateway = server_part
                    break
            elif tool_gateway_name == name:
                gateway_tool_name = tool_gateway_name
                break
        
        if not gateway_tool_name:
            return _json(
                200,
                {
                    "ok": False,
                    "tool": name,
                    "userId": user_id,
                    "arguments": arguments,
                    "error": {"code": -32601, "message": f"Tool '{name}' not found in gateway"},
                    "request": None,
                    "response": None,
                    "durationMs": _elapsed_ms(started),
                },
            )
        
        # Call the tool via gateway
        try:
            response = gateway_call_tool(gateway_url, session_id, gateway_tool_name, arguments, region)
            request = {"method": "tools/call", "params": {"name": gateway_tool_name, "arguments": arguments}}
        except McpClientError as exc:
            return _json(502, {"error": f"Gateway call failed: {exc}"})
        
        server = server_from_gateway
    else:
        # Direct-invoke (aggregator) mode
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


# --- admin: AI credits --------------------------------------------------------


def _user_view(profile: dict[str, Any], budget: quotas.Budget) -> dict[str, Any]:
    return {
        "userId": profile.get("userId"),
        "email": profile.get("email") or "",
        "fullName": profile.get("fullName") or "",
        "createdAt": profile.get("createdAt"),
        "isAdmin": bool(profile.get("isAdmin")),
        "budgetCredits": round(core_usage.usd_to_credits(budget.budget_micro_usd), 2),
        "spentCredits": round(core_usage.usd_to_credits(budget.spent_micro_usd), 2),
        "remainingCredits": None
        if budget.unlimited
        else round(core_usage.usd_to_credits(budget.remaining_micro_usd), 2),
        "unlimited": budget.unlimited,
    }


def _query(event: dict[str, Any]) -> dict[str, str]:
    from urllib.parse import parse_qs

    raw = event.get("rawQueryString") or ""
    if raw:
        parsed = parse_qs(raw)
        return {key: values[0] for key, values in parsed.items() if values}
    params = event.get("queryStringParameters") or {}
    return {key: str(value) for key, value in params.items() if value is not None}


def _encode_cursor(key: dict[str, Any] | None) -> str | None:
    if not key:
        return None
    import base64

    return base64.urlsafe_b64encode(json.dumps(key, default=str).encode()).decode()


def _decode_cursor(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    import base64

    try:
        return json.loads(base64.urlsafe_b64decode(value.encode()).decode())
    except Exception:  # noqa: BLE001 - a bad cursor just starts from the top
        return None


def _handle_list_users(event: dict[str, Any]) -> dict[str, Any]:
    query = _query(event)
    try:
        limit = int(query.get("limit") or 25)
    except ValueError:
        limit = 25
    items, next_key = list_users(limit, _decode_cursor(query.get("cursor")))
    budgets = quotas.get_budgets([str(item.get("userId") or "") for item in items])
    users = [
        _user_view(item, budgets.get(str(item.get("userId") or "")) or quotas.Budget(
            core_usage.default_budget_micro_usd(), 0, False
        ))
        for item in items
    ]
    return _json(
        200,
        {
            "users": users,
            "creditsPerUsd": core_usage.CREDITS_PER_USD,
            "defaultCredits": round(
                core_usage.usd_to_credits(core_usage.default_budget_micro_usd()), 2
            ),
            "nextCursor": _encode_cursor(next_key),
        },
    )


def _user_id_from_path(path: str) -> str | None:
    """``/v1/admin/users/<id>/credits`` -> ``<id>``."""
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) >= 2 and segments[-2] not in ("users",):
        return segments[-2]
    return None


def _handle_set_credits(event: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    user_id = _user_id_from_path(_path(event))
    if not user_id:
        return _json(400, {"error": "userId is required"})
    raw = body.get("credits")
    try:
        credits = float(raw)
    except (TypeError, ValueError):
        return _json(400, {"error": "credits must be a number"})
    if credits < 0:
        return _json(400, {"error": "credits must be zero or more"})
    quotas.set_budget_credits(user_id, credits)
    return _json(200, {"ok": True, **_user_view({"userId": user_id}, quotas.get_budget(user_id))})


def _handle_set_unlimited(event: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    user_id = _user_id_from_path(_path(event))
    if not user_id:
        return _json(400, {"error": "userId is required"})
    unlimited = body.get("unlimited")
    if not isinstance(unlimited, bool):
        return _json(400, {"error": "unlimited must be a boolean"})
    quotas.set_unlimited(user_id, unlimited)
    return _json(200, {"ok": True, **_user_view({"userId": user_id}, quotas.get_budget(user_id))})


def _handle_reset_credits(event: dict[str, Any]) -> dict[str, Any]:
    user_id = _user_id_from_path(_path(event))
    if not user_id:
        return _json(400, {"error": "userId is required"})
    quotas.reset_spend(user_id)
    return _json(200, {"ok": True, **_user_view({"userId": user_id}, quotas.get_budget(user_id))})


# --- admin: support inbox & security reports ----------------------------------


def _admin_ticket_view(ticket: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": ticket.get("ticketId"),
        "userId": ticket.get("userId"),
        "userEmail": ticket.get("userEmail") or "",
        "subject": ticket.get("subject") or "",
        "status": ticket.get("status") or support_repo.TICKET_OPEN,
        "createdAt": ticket.get("createdAt"),
        "updatedAt": ticket.get("updatedAt"),
        "messageCount": int(ticket.get("messageCount") or 0),
        "lastAuthor": ticket.get("lastAuthor") or support_repo.AUTHOR_USER,
        "lastMessage": ticket.get("lastMessage") or "",
    }


def _admin_message_view(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": message.get("messageId"),
        "author": message.get("author") or support_repo.AUTHOR_USER,
        "authorName": message.get("authorName") or "",
        "body": message.get("body") or "",
        "createdAt": message.get("createdAt"),
    }


def _admin_report_view(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": report.get("reportId"),
        "userId": report.get("userId"),
        "userEmail": report.get("userEmail") or "",
        "url": report.get("url") or "",
        "page": report.get("page") or "",
        "body": report.get("body") or "",
        "status": report.get("status") or support_repo.REPORT_NEW,
        "createdAt": report.get("createdAt"),
    }


def _admin_limit(event: dict[str, Any]) -> int:
    try:
        return int(_query(event).get("limit") or 25)
    except ValueError:
        return 25


def _handle_admin_support_list(event: dict[str, Any]) -> dict[str, Any]:
    items, next_key = support_repo.list_all_tickets(
        _admin_limit(event), _decode_cursor(_query(event).get("cursor"))
    )
    return _json(
        200,
        {
            "tickets": [_admin_ticket_view(item) for item in items],
            "nextCursor": _encode_cursor(next_key),
        },
    )


def _handle_admin_support_detail(user_id: str, ticket_id: str) -> dict[str, Any]:
    ticket = support_repo.get_ticket(user_id, ticket_id)
    if not ticket:
        return _json(404, {"error": "Ticket not found"})
    messages = support_repo.list_messages(ticket_id)
    return _json(
        200,
        {
            "ticket": _admin_ticket_view(ticket),
            "messages": [_admin_message_view(message) for message in messages],
        },
    )


def _handle_admin_support_reply(
    user_id: str, ticket_id: str, body: dict[str, Any], admin_name: str
) -> dict[str, Any]:
    ticket = support_repo.get_ticket(user_id, ticket_id)
    if not ticket:
        return _json(404, {"error": "Ticket not found"})
    message = str(body.get("body") or "").strip()
    if not message:
        return _json(400, {"error": "body is required"})
    if len(message) > support_repo.MAX_BODY:
        return _json(400, {"error": "body is too long"})
    created = support_repo.add_message(
        user_id,
        ticket_id,
        author=support_repo.AUTHOR_ADMIN,
        author_name=admin_name or "Support",
        body=message,
    )
    return _json(201, {"message": _admin_message_view(created)})


def _handle_admin_support_status(
    user_id: str, ticket_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    status = str(body.get("status") or "").strip()
    if status not in support_repo.TICKET_STATUSES:
        return _json(400, {"error": "status must be open or closed"})
    ticket = support_repo.set_ticket_status(user_id, ticket_id, status)
    if not ticket:
        return _json(404, {"error": "Ticket not found"})
    return _json(200, {"ticket": _admin_ticket_view(ticket)})


def _handle_admin_security_list(event: dict[str, Any]) -> dict[str, Any]:
    items, next_key = support_repo.list_all_security_reports(
        _admin_limit(event), _decode_cursor(_query(event).get("cursor"))
    )
    return _json(
        200,
        {
            "reports": [_admin_report_view(item) for item in items],
            "nextCursor": _encode_cursor(next_key),
        },
    )


def _handle_admin_security_detail(user_id: str, report_id: str) -> dict[str, Any]:
    report = support_repo.get_security_report(user_id, report_id)
    if not report:
        return _json(404, {"error": "Report not found"})
    return _json(200, {"report": _admin_report_view(report)})


def _handle_admin_security_status(
    user_id: str, report_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    status = str(body.get("status") or "").strip()
    if status not in support_repo.REPORT_STATUSES:
        return _json(400, {"error": "status must be new or resolved"})
    report = support_repo.set_report_status(user_id, report_id, status)
    if not report:
        return _json(404, {"error": "Report not found"})
    return _json(200, {"report": _admin_report_view(report)})


def _route_admin_inbox(
    event: dict[str, Any], method: str, segments: list[str], admin_name: str
) -> dict[str, Any] | None:
    """Dispatch the admin support/security routes; ``None`` when unmatched."""
    if segments[:3] == ["v1", "admin", "support"]:
        rest = segments[3:]
        if not rest:
            if method == "GET":
                return _handle_admin_support_list(event)
            return _json(405, {"error": f"Method not allowed: {method}"})
        if len(rest) == 2 and method == "GET":
            return _handle_admin_support_detail(rest[0], rest[1])
        if len(rest) == 3 and rest[2] == "reply" and method == "POST":
            return _handle_admin_support_reply(
                rest[0], rest[1], _body(event), admin_name
            )
        if len(rest) == 3 and rest[2] == "status" and method == "POST":
            return _handle_admin_support_status(rest[0], rest[1], _body(event))
        return _json(404, {"error": "Not found"})

    if segments[:3] == ["v1", "admin", "security-reports"]:
        rest = segments[3:]
        if not rest:
            if method == "GET":
                return _handle_admin_security_list(event)
            return _json(405, {"error": f"Method not allowed: {method}"})
        if len(rest) == 2 and method == "GET":
            return _handle_admin_security_detail(rest[0], rest[1])
        if len(rest) == 3 and rest[2] == "status" and method == "POST":
            return _handle_admin_security_status(rest[0], rest[1], _body(event))
        return _json(404, {"error": "Not found"})

    return None


# --- admin: platform status ---------------------------------------------------
#
# AgentCore Identity/Registry/Browser/Optimization and the Bedrock levers. These
# are the admin-console counterparts of the user-facing Platform status routes
# (which keep only Identity + Browser); the admin console gets the full set.
# All handlers call the same shared ``core.*`` helpers the user-api uses.


def _platform_identity(
    claims: dict[str, Any], method: str, rest: list[str], body: dict[str, Any]
) -> dict[str, Any]:
    from core import identity

    if not rest:
        if method == "GET":
            get_or_create_user(claims)
            return _json(200, identity.describe())
        return _json(405, {"error": f"Method not allowed: {method}"})
    if rest[0] == "token" and method == "POST":
        profile = get_or_create_user(claims)
        provider = str(body.get("provider") or "").strip()
        if not provider:
            return _json(400, {"error": "provider is required"})
        scopes = body.get("scopes")
        scope_list = (
            [str(value) for value in scopes if str(value).strip()]
            if isinstance(scopes, list)
            else []
        )
        if not identity.enabled():
            return _json(400, {"error": "AgentCore Identity is not configured"})
        try:
            token = identity.get_token(
                profile["userId"], provider, scopes=scope_list or None
            )
        except RuntimeError as exc:
            return _json(400, {"error": str(exc)[:300]})
        except Exception as exc:  # noqa: BLE001 - provider/authorization failure
            return _json(502, {"error": f"Identity token request failed: {exc}"})
        # Never echo a live token; only its shape/lifetime.
        return _json(
            200,
            {
                "provider": provider,
                "obtained": bool(token.get("accessToken")),
                "expiresAt": token.get("expiresAt"),
                "scopes": token.get("scopes") or scope_list,
            },
        )
    return _json(404, {"error": "Not found"})


def _platform_registry(
    claims: dict[str, Any],
    event: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
) -> dict[str, Any]:
    from core import registry as agent_registry

    profile = get_or_create_user(claims)

    if not rest:
        if method == "GET":
            return _json(200, agent_registry.describe())
        return _json(405, {"error": f"Method not allowed: {method}"})

    if rest[0] == "publish" and method == "POST":
        if not agent_registry.enabled():
            return _json(400, {"error": "AgentCore Registry is not configured"})
        name = str(body.get("name") or "").strip()
        if not name:
            return _json(400, {"error": "name is required"})
        record_type = str(body.get("recordType") or "AGENT").strip().upper()
        if record_type not in ("AGENT", "MCP_SERVER", "TOOL", "SKILL"):
            return _json(
                400, {"error": "recordType must be AGENT, MCP_SERVER, TOOL or SKILL"}
            )
        metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
        try:
            created = agent_registry.publish(
                name=name,
                description=str(body.get("description") or ""),
                record_type=record_type,
                metadata={"owner": profile["userId"], **metadata},
            )
        except Exception as exc:  # noqa: BLE001 - surface a clean error
            return _json(502, {"error": f"Publish failed: {exc}"})
        return _json(201, {"ok": True, "record": created})

    if rest[0] == "search" and method == "GET":
        if not agent_registry.enabled():
            return _json(200, {"configured": False, "records": []})
        records = agent_registry.search(_query(event).get("q") or "", limit=20)
        return _json(200, {"configured": True, "records": records})

    return _json(404, {"error": "Not found"})


def _platform_browser(
    claims: dict[str, Any], method: str, rest: list[str], body: dict[str, Any]
) -> dict[str, Any]:
    from core import browser

    get_or_create_user(claims)

    if not rest:
        if method == "GET":
            return _json(200, browser.describe())
        return _json(405, {"error": f"Method not allowed: {method}"})

    if rest[0] == "check" and method == "POST":
        url = str(body.get("url") or "").strip()
        if not url:
            return _json(400, {"error": "url is required"})
        allowed, reason = browser.allowed(url)
        return _json(200, {"allowed": allowed, "reason": reason})

    # Order matters: the exact `session/close` route must be matched before the
    # generic `session` route, which would otherwise swallow it.
    if rest == ["session", "close"] and method == "POST":
        session_id = str(body.get("sessionId") or "").strip()
        if not session_id:
            return _json(400, {"error": "sessionId is required"})
        return _json(200, {"stopped": browser.stop_session(session_id)})

    if rest == ["session"] and method == "POST":
        url = str(body.get("url") or "").strip()
        if not url:
            return _json(400, {"error": "url is required"})
        if not browser.enabled():
            return _json(400, {"error": "AgentCore Browser is not configured"})
        allowed, reason = browser.allowed(url)
        if not allowed:
            return _json(403, {"error": reason})
        try:
            return _json(200, browser.start_session())
        except Exception as exc:  # noqa: BLE001
            return _json(502, {"error": f"Browser session failed: {exc}"})

    if rest == ["session"] and method == "DELETE":
        session_id = str(body.get("sessionId") or "").strip()
        if not session_id:
            return _json(400, {"error": "sessionId is required"})
        return _json(200, {"stopped": browser.stop_session(session_id)})

    return _json(404, {"error": "Not found"})


def _platform_optimization(claims: dict[str, Any], method: str) -> dict[str, Any]:
    from core import optimization

    get_or_create_user(claims)
    if method != "GET":
        return _json(405, {"error": f"Method not allowed: {method}"})
    return _json(200, optimization.describe())


def _platform_bedrock_features(claims: dict[str, Any], method: str) -> dict[str, Any]:
    from core import bedrock_features

    get_or_create_user(claims)
    if method != "GET":
        return _json(405, {"error": f"Method not allowed: {method}"})
    return _json(200, bedrock_features.describe())


def _platform_network(
    claims: dict[str, Any], method: str, body: dict[str, Any]
) -> dict[str, Any]:
    """Platform network-tools kill switch + the limits currently in force."""
    from core import network
    from data.repositories import platform as platform_repo

    settings = platform_repo.get_settings()
    if method == "GET":
        payload = network.describe(enabled_override=settings["networkToolsEnabled"])
        payload["updatedAt"] = settings.get("updatedAt")
        payload["updatedBy"] = settings.get("updatedBy")
        return _json(200, payload)
    if method != "POST":
        return _json(405, {"error": f"Method not allowed: {method}"})
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        return _json(400, {"error": "enabled (boolean) is required"})
    updated_by = str(
        claims.get("name")
        or claims.get("https://get1agent.com/email")
        or claims.get("email")
        or "admin"
    )
    updated = platform_repo.set_network_tools_enabled(enabled, updated_by=updated_by)
    payload = network.describe(enabled_override=updated["networkToolsEnabled"])
    payload["updatedAt"] = updated.get("updatedAt")
    payload["updatedBy"] = updated.get("updatedBy")
    return _json(200, payload)


def _route_platform(
    event: dict[str, Any],
    claims: dict[str, Any],
    method: str,
    segments: list[str],
    body: dict[str, Any],
) -> dict[str, Any] | None:
    """Dispatch the admin platform-status routes; ``None`` when unmatched."""
    if segments[:3] != ["v1", "admin", "platform"]:
        return None
    rest = segments[3:]
    if not rest:
        return _json(
            200,
            {
                "services": [
                    "identity",
                    "registry",
                    "browser",
                    "optimization",
                    "bedrock-features",
                    "network",
                ]
            },
        )
    service, sub = rest[0], rest[1:]
    if service == "identity":
        return _platform_identity(claims, method, sub, body)
    if service == "registry":
        return _platform_registry(claims, event, method, sub, body)
    if service == "browser":
        return _platform_browser(claims, method, sub, body)
    if service == "optimization":
        return _platform_optimization(claims, method)
    if service == "bedrock-features":
        return _platform_bedrock_features(claims, method)
    if service == "network":
        return _platform_network(claims, method, body)
    return _json(404, {"error": "Not found"})


def lambda_handler(event: dict[str, Any], _context) -> dict[str, Any]:
    event = event if isinstance(event, dict) else {}

    claims = _claims(event)
    if not claims:
        return _json(401, {"error": "Unauthorized"})
    try:
        require_admin(claims, event)
    except AuthError as exc:
        return _json(exc.status, {"error": exc.message})

    method = _method(event)
    path = _path(event)
    segments = [segment for segment in path.split("/") if segment]
    admin_name = str(
        claims.get("name")
        or claims.get("https://get1agent.com/email")
        or claims.get("email")
        or "Support"
    )

    # Admin credit management works even when no MCP functions are configured.
    try:
        inbox = _route_admin_inbox(event, method, segments, admin_name)
        if inbox is not None:
            return inbox
        if segments[:3] == ["v1", "admin", "platform"]:
            return _route_platform(event, claims, method, segments, _body(event))
        if method == "GET" and path.endswith("/admin/users"):
            return _handle_list_users(event)
        if method == "POST" and path.endswith("/credits"):
            return _handle_set_credits(event, _body(event))
        if method == "POST" and path.endswith("/reset"):
            return _handle_reset_credits(event)
        if method == "POST" and path.endswith("/unlimited"):
            return _handle_set_unlimited(event, _body(event))
    except Exception as exc:  # noqa: BLE001
        print(f"admin-console admin error: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        return _json(500, {"error": "Internal server error"})

    functions = _mcp_functions()
    if not functions:
        return _json(500, {"error": "MCP_FUNCTIONS is not configured"})
    region = os.environ.get("AWS_REGION")
    sub = str(claims.get("sub") or "").strip()
    profile = _resolve_user(claims, sub)
    user_id = str(profile.get("userId") or sub).strip()

    try:
        # Get transport mode and gateway URL
        transport = _mcp_transport()
        gateway = _gateway_url()
        # Generate a session ID for gateway calls (can be empty for stateless calls)
        session_id = f"admin-{user_id}-{int(time.time())}"
        
        if method == "GET" and path.endswith("/mcp/tools"):
            return _handle_list_tools(functions, user_id, region, transport, gateway, session_id)
        if method == "POST" and path.endswith("/mcp/call"):
            return _handle_call_tool(functions, user_id, region, _body(event), transport, gateway, session_id)
        return _json(404, {"error": "Not found"})
    except (McpClientError, ValueError) as exc:
        return _json(502, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        print(f"admin-console error: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        return _json(500, {"error": "Internal server error"})
