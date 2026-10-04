"""Browser tool logic (AgentCore Browser).

Exposes the tool schemas and implementations plus the domain-allowlist gate. The
MCP wiring lives in ``handler.py`` (which uses the shared ``build_handler``), so
this module stays free of Lambda plumbing and is directly unit-testable.
"""

from __future__ import annotations

from typing import Any

from core import browser

OPEN_TOOL = "open-browser-session"
CLOSE_TOOL = "close-browser-session"

# Tools that need no signed-in user (none for now).
_PUBLIC_TOOLS: set[str] = set()

_OPEN_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "Absolute http(s) URL to open"},
        "reason": {"type": "string", "description": "Why the page is needed (logged)"},
    },
    "required": ["url"],
}

_CLOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "sessionId": {"type": "string", "description": "Session id from open-browser-session"},
    },
    "required": ["sessionId"],
}


def _error(code: str, message: str, status: int = 400) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}, "status": status}


def open_browser_session(args: dict[str, Any]) -> dict[str, Any]:
    url = str(args.get("url") or "").strip()
    if not url:
        return _error("invalid_request", "url is required")
    if not browser.enabled():
        return _error("not_configured", "AgentCore Browser is not configured", 503)

    permitted, reason = browser.allowed(url)
    if not permitted:
        return _error("domain_not_allowed", reason, 403)

    try:
        session = browser.start_session()
    except Exception as exc:  # noqa: BLE001 - surface a clean tool error
        return _error("browser_error", str(exc)[:300], 502)

    return {
        "ok": True,
        "url": url,
        "sessionId": session["sessionId"],
        "browserId": session["browserId"],
        "liveViewUrl": session.get("liveViewUrl"),
        "wsHeaders": session.get("wsHeaders") or {},
    }


def close_browser_session(args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("sessionId") or "").strip()
    if not session_id:
        return _error("invalid_request", "sessionId is required")
    return {"ok": True, "stopped": browser.stop_session(session_id)}


def tool_schemas() -> dict[str, dict[str, Any]]:
    return {OPEN_TOOL: _OPEN_SCHEMA, CLOSE_TOOL: _CLOSE_SCHEMA}


def status() -> dict[str, Any]:
    return browser.describe()

