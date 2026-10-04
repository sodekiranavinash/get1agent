"""AgentCore Browser helper (managed cloud browser).

Opens a managed browser session through Amazon Bedrock AgentCore Browser and
returns its live-view / automation endpoints, so an agent can operate JS-heavy or
form-driven pages that a static fetch cannot render.

Domain access is a policy decision: :func:`allowed` gates a URL against
``BROWSER_ALLOWED_DOMAINS`` and is called by the browser tool before a session
starts, so an agent can never drive a page nobody approved.

Best-effort by default: without ``BROWSER_ID`` every helper reports "not
configured" and the tool is not offered.

Config: ``BROWSER_ID``, ``BROWSER_REGION``, ``BROWSER_ALLOWED_DOMAINS``
(comma-separated suffixes; empty denies everything), ``BROWSER_SESSION_TIMEOUT``.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

DEFAULT_TIMEOUT = 900


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def browser_id() -> str:
    return _env("BROWSER_ID")


def region() -> str:
    return _env("BROWSER_REGION") or _env("BEDROCK_REGION") or _env("AWS_REGION") or "ap-south-1"


def session_timeout() -> int:
    try:
        return max(int(_env("BROWSER_SESSION_TIMEOUT", str(DEFAULT_TIMEOUT))), 60)
    except ValueError:
        return DEFAULT_TIMEOUT


def enabled() -> bool:
    return bool(browser_id())


def allowed_domains() -> list[str]:
    raw = _env("BROWSER_ALLOWED_DOMAINS")
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def allowed(url: str) -> tuple[bool, str]:
    """Gate a URL against the domain allowlist (fail closed)."""
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return False, "a valid absolute URL is required"
    allow = allowed_domains()
    if not allow:
        return False, "browser access is not allowed for this workspace"
    for suffix in allow:
        if host == suffix or host.endswith(f".{suffix}"):
            return True, ""
    return False, f'domain "{host}" is not in the browser allowlist'


def _client() -> Any:
    from bedrock_agentcore.tools.browser_client import BrowserClient

    return BrowserClient(region=region())


def start_session() -> dict[str, Any]:
    """Start a browser session; returns its id plus automation endpoints."""
    if not enabled():
        raise RuntimeError("AgentCore Browser is not configured")
    client = _client()
    session = client.start(identifier=browser_id(), session_timeout_seconds=session_timeout())
    client.session_id = session.get("sessionId") or client.session_id
    headers: dict[str, str] = {}
    try:
        _, headers = client.generate_ws_headers()
    except Exception:  # noqa: BLE001 - headers are optional for a scripted run
        headers = {}
    return {
        "sessionId": client.session_id,
        "browserId": browser_id(),
        "liveViewUrl": _safe_live_view(client),
        "wsHeaders": headers,
    }


def _safe_live_view(client: Any) -> str | None:
    try:
        return client.generate_live_view_url()
    except Exception:  # noqa: BLE001
        return None


def stop_session(session_id: str) -> bool:
    """Stop a browser session (idempotent, best-effort)."""
    if not enabled() or not session_id:
        return False
    try:
        client = _client()
        client.session_id = session_id
        return bool(client.stop())
    except Exception:  # noqa: BLE001
        return False


def describe() -> dict[str, Any]:
    return {
        "configured": enabled(),
        "browserId": browser_id() or None,
        "region": region(),
        "allowedDomains": allowed_domains(),
        "sessionTimeout": session_timeout(),
    }
