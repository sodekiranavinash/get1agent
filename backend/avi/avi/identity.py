"""Who is asking, and how Avi proves it.

Two callers, two mechanisms, one rule: **identity never comes from the request
body**.

* **Signed-in** — the control-plane Lambda already had the Auth0 JWT verified by
  API Gateway, so it mints a short-lived, HMAC-signed *session token* carrying the
  internal ``userId``. The agent service verifies that signature (and refuses an
  expired one), so a caller cannot forge a userId by editing the payload. The JWT
  is never forwarded to the model service.
* **Guest** — there is no account. The ingress passes an explicit guest marker and
  the caller's IP, and this module derives a stable **hashed** key from it. The raw
  IP is never stored or logged; only the hash is used, and only as a rate-limit
  bucket.

Local development runs the same code with ``AVI_SESSION_SECRET`` set from the
environment, so there is no separate "insecure dev mode" that could reach prod.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from data.repositories.users import get_user_by_sub

from avi.limits import Caller, SURFACE_GUEST, SURFACE_USER

DEFAULT_TTL_SECONDS = 900


class IdentityError(PermissionError):
    """The caller's identity could not be established."""


@dataclass(frozen=True)
class Identity:
    """A resolved caller."""

    user_id: str
    sub: str = ""
    email: str = ""
    name: str = ""
    is_admin: bool = False
    is_guest: bool = False

    @property
    def surface(self) -> str:
        return SURFACE_GUEST if self.is_guest else SURFACE_USER

    def to_caller(self) -> Caller:
        return Caller(
            key=self.rate_key(),
            surface=self.surface,
            user_id=self.user_id,
            is_admin=self.is_admin,
        )

    def rate_key(self) -> str:
        """The rate-limit bucket: the userId, or the guest hash."""
        return self.user_id


def _secret() -> bytes:
    raw = (
        os.environ.get("AVI_SESSION_SECRET")
        or os.environ.get("AGENT_SERVICE_CLIENT_SECRET")
        or ""
    ).strip()
    if not raw:
        raise IdentityError("Avi session signing is not configured")
    return raw.encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def mint_session_token(
    *,
    user_id: str,
    sub: str = "",
    email: str = "",
    name: str = "",
    is_admin: bool = False,
    is_guest: bool = False,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Mint the short-lived session token the control plane hands to the agent.

    Called by the control-plane Lambda (and by local dev). The payload is signed,
    not encrypted — it carries no secret, only who the caller is, and the
    signature is what makes it trustworthy.

    A **guest badge** is the same mechanism with ``is_guest``: the ingress proved
    the caller is a guest (and paid the rate-limit cost), and the agent service
    only has to verify the signature. That is what lets the MicroVM serve both
    audiences through one verified code path.
    """
    now = int(time.time())
    payload = {
        "sub": sub,
        "userId": user_id,
        "email": email,
        "name": name,
        "admin": bool(is_admin),
        "guest": bool(is_guest),
        "iat": now,
        "exp": now + max(60, int(ttl_seconds)),
    }
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return f"avi1.{body}.{_b64(signature)}"


def verify_session_token(token: str) -> Identity:
    """Verify a session token, or raise :class:`IdentityError`."""
    parts = str(token or "").split(".")
    if len(parts) != 3 or parts[0] != "avi1":
        raise IdentityError("Malformed Avi session token")
    _, body, signature = parts
    expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
    try:
        provided = _unb64(signature)
    except Exception as exc:  # noqa: BLE001
        raise IdentityError("Malformed Avi session token") from exc
    if not hmac.compare_digest(expected, provided):
        raise IdentityError("Invalid Avi session token")

    try:
        payload = json.loads(_unb64(body))
    except Exception as exc:  # noqa: BLE001
        raise IdentityError("Malformed Avi session token payload") from exc
    if not isinstance(payload, dict):
        raise IdentityError("Malformed Avi session token payload")

    if int(payload.get("exp") or 0) < int(time.time()):
        raise IdentityError("Avi session expired — reopen Avi")

    user_id = str(payload.get("userId") or "").strip()
    if not user_id:
        raise IdentityError("Avi session token has no user")

    return Identity(
        user_id=user_id,
        sub=str(payload.get("sub") or ""),
        email=str(payload.get("email") or ""),
        name=str(payload.get("name") or ""),
        is_admin=bool(payload.get("admin")),
        is_guest=bool(payload.get("guest")),
    )


def guest_identity(ip: str, *, salt: str = "") -> Identity:
    """A stable, non-reversible bucket key for an unauthenticated caller."""
    material = f"{salt or os.environ.get('AVI_GUEST_SALT', 'avi')}|{ip or 'unknown'}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    return Identity(user_id=f"guest_{digest}", is_guest=True)


def bearer_token(header: str | None) -> str:
    raw = str(header or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


def resolve_identity(
    authorization: str | None,
    *,
    allow_guest: bool = False,
    client_ip: str = "",
) -> Identity:
    """Resolve the caller from the Authorization header.

    Accepts the control plane's session token. A raw Auth0 JWT is **not** accepted
    here: verifying it would mean fetching and caching JWKS in a service that
    already receives a verified identity, and duplicating that logic is how the
    two paths drift apart.
    """
    token = bearer_token(authorization)
    if not token:
        if allow_guest:
            return guest_identity(client_ip)
        raise IdentityError("Sign in to ask Avi")
    return verify_session_token(token)


def identity_from_sub(sub: str) -> Identity:
    """Resolve an Auth0 ``sub`` to the internal user (the control plane's job).

    Used by the control-plane Lambda and the guest/eval tools; it performs the
    strongly-consistent ``SUB#<sub>`` lookup that maps an identity to a userId.
    """
    normalized = str(sub or "").strip()
    if not normalized:
        raise IdentityError("Token has no subject")
    profile = get_user_by_sub(normalized)
    if not profile:
        raise IdentityError("No account found for this identity")
    claims_roles = profile.get("roles") or []
    return Identity(
        user_id=str(profile.get("userId") or ""),
        sub=normalized,
        email=str(profile.get("email") or ""),
        name=str(profile.get("name") or ""),
        is_admin=any(str(role).lower() == "admin" for role in claims_roles),
    )


def describe(identity: Identity) -> dict[str, Any]:
    """A safe summary for a trace (never the token, never the raw IP)."""
    return {
        "userId": identity.user_id,
        "surface": identity.surface,
        "admin": identity.is_admin,
    }
