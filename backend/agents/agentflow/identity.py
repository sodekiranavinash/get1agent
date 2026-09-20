"""Resolve the caller's internal ``userId`` from the AgentCore request context.

In production the runtime is configured with a custom JWT authorizer (Auth0),
so AgentCore validates the bearer token before the request reaches the
container; the ``Authorization`` header is forwarded (allowlisted). We only need
to decode the (already verified) JWT payload to read the ``sub`` and map it to
the internal short ``userId`` via the ``SUB#<sub>`` identity item.

Local development (no authorizer) may pass ``userId`` directly in the payload.
"""

from __future__ import annotations

import base64
import json
from typing import Any


def _bearer(value: str | None) -> str:
    if not value:
        return ""
    parts = value.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return value.strip()


def decode_jwt_sub(token: str) -> str | None:
    """Read ``sub`` from an unverified JWT payload (signature is AgentCore's job)."""
    if not token or token.count(".") != 2:
        return None
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except Exception:  # noqa: BLE001 - malformed token
        return None
    sub = data.get("sub")
    return str(sub) if sub else None


def _headers(context: Any) -> dict[str, str]:
    headers = getattr(context, "request_headers", None) or {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


def resolve_user_id(payload: dict[str, Any], context: Any) -> str:
    """Return the internal userId for this invocation.

    Raises ``ValueError`` when the caller cannot be identified.
    """
    token = _bearer(_headers(context).get("authorization"))
    sub = decode_jwt_sub(token)
    if sub:
        from data.repositories import users

        profile = users.get_user_by_sub(sub)
        if profile is None:
            raise ValueError("Unknown user")
        return str(profile["userId"])

    # Local/dev fallback: the trusted caller passes the internal id directly.
    user_id = str(payload.get("userId") or "").strip()
    if not user_id:
        raise ValueError("Missing credentials")
    return user_id
