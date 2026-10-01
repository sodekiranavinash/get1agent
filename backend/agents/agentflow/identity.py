"""Resolve the caller's internal ``userId`` from the AgentCore request context.

In production the runtime is configured with a custom JWT authorizer (Auth0),
so AgentCore validates the bearer token before the request reaches the
container; the ``Authorization`` header is forwarded (allowlisted). We decode
the (already verified) JWT payload to read the ``sub`` and map it to the
internal short ``userId`` via the ``SUB#<sub>`` identity item.

**Service callers** (the background evaluation worker) authenticate with an
Auth0 client-credentials token whose ``sub`` is ``<client_id>@clients``. When
that client id matches ``SERVICE_AUTH_CLIENT_ID`` the invocation is trusted and
the target ``userId`` is read from the payload instead of the token — this is
what lets evaluations run agents server-side without a human's JWT.

Local development (no authorizer) may pass ``userId`` directly in the payload.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any


def _bearer(value: str | None) -> str:
    if not value:
        return ""
    parts = value.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return value.strip()


def decode_jwt_claims(token: str) -> dict[str, Any] | None:
    """Decode an unverified JWT payload (signature is AgentCore's job)."""
    if not token or token.count(".") != 2:
        return None
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except Exception:  # noqa: BLE001 - malformed token
        return None
    return data if isinstance(data, dict) else None


def decode_jwt_sub(token: str) -> str | None:
    """Read ``sub`` from an unverified JWT payload."""
    claims = decode_jwt_claims(token)
    sub = (claims or {}).get("sub")
    return str(sub) if sub else None


def _headers(context: Any) -> dict[str, str]:
    headers = getattr(context, "request_headers", None) or {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _is_service_sub(sub: str) -> bool:
    """True when ``sub`` is the configured platform service client."""
    client_id = (os.environ.get("SERVICE_AUTH_CLIENT_ID") or "").strip()
    return bool(client_id) and sub == f"{client_id}@clients"


def resolve_user_id(payload: dict[str, Any], context: Any) -> str:
    """Return the internal userId for this invocation.

    Raises ``ValueError`` when the caller cannot be identified.
    """
    token = _bearer(_headers(context).get("authorization"))
    claims = decode_jwt_claims(token)
    if claims:
        sub = str(claims.get("sub") or "")
        if sub and _is_service_sub(sub):
            # Trusted platform caller: the target user travels in the payload.
            user_id = str(payload.get("userId") or "").strip()
            if user_id:
                return user_id
            raise ValueError("Missing userId for service invocation")
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
