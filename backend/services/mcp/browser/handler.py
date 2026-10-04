"""browser MCP server Lambda.

Exposes the ``browser`` capability as one MCP server backed by **AgentCore
Browser**:

* ``open-browser-session`` — open a managed browser session for an approved URL.
* ``close-browser-session`` — stop a session.

The domain allowlist is enforced in the tool; the AgentCore Policy guard is a
second gate on the ``browser`` tool name.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from awslabs.mcp_lambda_handler import MCPLambdaHandler

from core.mcp_server import build_handler, require_sub
from src import service

mcp = MCPLambdaHandler(name="get1agent-browser", version="1.0.0")


def _run(tool: str, handler: Any, sub: str | None, params: dict[str, Any] | None = None) -> str:
    try:
        args = dict(params or {})
        if sub is not None:
            args["userId"] = sub
        if sub is None and tool not in service._PUBLIC_TOOLS:  # noqa: SLF001
            result = service._error("unauthorized", "A signed-in user is required", 401)  # noqa: SLF001
        else:
            result = handler(args)
    except Exception:  # noqa: BLE001 - never leak a stack to the model
        traceback.print_exc()
        result = service._error("internal_error", "Request failed")  # noqa: SLF001
    return json.dumps(result, default=str)


def open_browser_session(url: str, reason: str | None = None) -> str:
    """Open an AgentCore Browser session for an allowlisted URL."""
    return _run(
        service.OPEN_TOOL,
        service.open_browser_session,
        require_sub(),
        {"url": url, "reason": reason},
    )


def close_browser_session(sessionId: str) -> str:
    """Stop a browser session."""
    return _run(
        service.CLOSE_TOOL,
        service.close_browser_session,
        require_sub(),
        {"sessionId": sessionId},
    )


mcp.tools[service.OPEN_TOOL] = service.tool_schemas()[service.OPEN_TOOL]
mcp.tool_implementations[service.OPEN_TOOL] = open_browser_session
mcp.tools[service.CLOSE_TOOL] = service.tool_schemas()[service.CLOSE_TOOL]
mcp.tool_implementations[service.CLOSE_TOOL] = close_browser_session


def _resolve_user_id(sub: str) -> str | None:
    try:
        from data.repositories.users import get_user_by_sub

        profile = get_user_by_sub(sub)
        return str(profile["userId"]) if profile else None
    except Exception:  # noqa: BLE001
        return None


lambda_handler = build_handler(mcp, resolve_user_id=_resolve_user_id)
