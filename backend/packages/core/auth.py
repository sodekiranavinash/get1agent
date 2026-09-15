"""Auth0 role + active-view checks.

The Auth0 Login Action copies the user's roles onto both the ID token and the
access token under namespaced custom claims (Auth0 requires a namespace for
custom claims). API Gateway forwards the access-token claims to every Lambda.

A user may hold several roles (e.g. ``admin``), so after login the SPA asks
which **view** to enter and sends it on every request as ``x-active-view``.
The server validates that view against the token's actual roles, so a normal
user can never claim the admin view:

* ``require_admin(claims, event)`` — admin role **and** the admin view.
* ``require_user(claims, event)``  — the user view (admins may pick it too,
  which is how an admin adds data before testing it).
"""

from __future__ import annotations

import json
from typing import Any

NAMESPACE = "https://get1agent.com/"
ADMIN_CLAIM = f"{NAMESPACE}isAdmin"
ROLES_CLAIM = f"{NAMESPACE}roles"
ADMIN_ROLE = "admin"

VIEW_HEADER = "x-active-view"
VIEW_USER = "user"
VIEW_ADMIN = "admin"


class AuthError(Exception):
    """Raised when a caller is not allowed to use the requested surface."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _claim(claims: dict[str, Any], name: str) -> Any:
    """Read a namespaced custom claim, falling back to the bare name."""
    return claims.get(f"{NAMESPACE}{name}", claims.get(name))


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().strip("[]").strip('"').strip("'").strip().lower() in {
            "true",
            "1",
            "yes",
        }
    return False


def _clean_role(value: Any) -> str:
    text = str(value).strip()
    for _ in range(3):
        text = text.strip('"').strip("'").strip("[]").strip()
    return text.lower()


def _normalize_roles(raw: Any) -> list[str]:
    """Accept roles as a list, a JSON array string, ``[admin]``, or CSV.

    Auth0 Actions/claims are not always shaped as a clean list — e.g. a claim
    may arrive as the literal string ``"[admin]"``. Normalise all of them so a
    token that clearly carries ``admin`` is recognised.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if parsed is not None and parsed != raw:
            return _normalize_roles(parsed)
        return [role for role in (_clean_role(part) for part in text.split(",")) if role]
    if isinstance(raw, (list, tuple, set)):
        roles: list[str] = []
        for item in raw:
            roles.extend(_normalize_roles(item) if isinstance(item, str) else [c for c in [_clean_role(item)] if c])
        return roles
    cleaned = _clean_role(raw)
    return [cleaned] if cleaned else []


def token_roles(claims: dict[str, Any] | None) -> list[str]:
    if not claims:
        return []
    return _normalize_roles(_claim(claims, "roles"))


def is_admin_claims(claims: dict[str, Any] | None) -> bool:
    """True when the token carries the admin flag or the ``admin`` role."""
    if not claims:
        return False
    if _as_bool(_claim(claims, "isAdmin")):
        return True
    return ADMIN_ROLE in token_roles(claims)


def _header(event: dict[str, Any], name: str) -> str | None:
    headers = event.get("headers") if isinstance(event, dict) else None
    if not isinstance(headers, dict):
        return None
    for key, value in headers.items():
        if str(key).lower() == name and value is not None:
            return str(value).strip().lower()
    return None


def active_view(event: dict[str, Any], claims: dict[str, Any] | None) -> str:
    """The requested view, falling back to the token's own role."""
    requested = _header(event, VIEW_HEADER)
    if requested in (VIEW_USER, VIEW_ADMIN):
        return requested
    return VIEW_ADMIN if is_admin_claims(claims) else VIEW_USER


def require_admin(claims: dict[str, Any] | None, event: dict[str, Any]) -> None:
    if not claims:
        raise AuthError(401, "Unauthorized")
    if not is_admin_claims(claims):
        roles = token_roles(claims)
        # Include the roles the *access token* carried: this is the caller's own
        # token, and it makes an Action/claim misconfiguration obvious.
        raise AuthError(
            403,
            "Admin access required (access-token roles: "
            f"{roles if roles else 'none'})",
        )
    if active_view(event, claims) != VIEW_ADMIN:
        raise AuthError(403, "Switch to the admin view to use this API")


def require_user(claims: dict[str, Any] | None, event: dict[str, Any]) -> None:
    if not claims:
        raise AuthError(401, "Unauthorized")
    if active_view(event, claims) != VIEW_USER:
        raise AuthError(403, "Switch to the user view to use this API")
