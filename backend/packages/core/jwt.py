"""Verify Auth0 access tokens (RS256) against the tenant JWKS.

The ``agent-run`` proxy calls :func:`verify_token` **before** it invokes
AgentCore, so an unauthenticated request never starts a runtime session. The
AgentCore runtime re-validates the same token with its inbound JWT authorizer;
this is the fail-fast gate in front of it.

Configuration (environment):

* ``AUTH0_DISCOVERY_URL`` — OIDC discovery document (required). The issuer and
  ``jwks_uri`` are read from it.
* ``AUTH0_AUDIENCE`` — comma-separated allowed audiences (the API identifier).
* ``AUTH0_ISSUER`` — optional issuer override (handy for tests/local dev).
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from typing import Any

import jwt  # PyJWT

# Discovery/JWKS documents are cached in the execution environment. JWKS is
# short-lived because Auth0 rotates signing keys.
_DISCOVERY_TTL_SECONDS = 3600
_JWKS_TTL_SECONDS = 300

_lock = threading.Lock()
_cache: dict[str, Any] = {
    "discovery": None,
    "discovery_at": 0.0,
    "jwks": None,
    "jwks_at": 0.0,
}


class TokenError(Exception):
    """Raised when a bearer token is missing, malformed, or not valid."""


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _audience() -> list[str]:
    raw = _env("AUTH0_AUDIENCE")
    return [part.strip() for part in raw.split(",") if part.strip()]


def _discovery_url() -> str:
    url = _env("AUTH0_DISCOVERY_URL")
    if not url:
        raise TokenError("AUTH0_DISCOVERY_URL is not configured")
    return url


def _get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"accept": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _discovery() -> dict[str, Any]:
    with _lock:
        cached = _cache["discovery"]
        if cached is not None and time.time() - _cache["discovery_at"] < _DISCOVERY_TTL_SECONDS:
            return cached
    document = _get_json(_discovery_url())
    with _lock:
        _cache["discovery"] = document
        _cache["discovery_at"] = time.time()
    return document


def _fetch_jwks() -> dict[str, Any]:
    with _lock:
        cached = _cache["jwks"]
        if cached is not None and time.time() - _cache["jwks_at"] < _JWKS_TTL_SECONDS:
            return cached
    uri = str(_discovery().get("jwks_uri") or "")
    if not uri:
        raise TokenError("discovery document has no jwks_uri")
    document = _get_json(uri)
    with _lock:
        _cache["jwks"] = document
        _cache["jwks_at"] = time.time()
    return document


def _issuer() -> str:
    override = _env("AUTH0_ISSUER")
    if override:
        return override
    return str(_discovery().get("issuer") or "")


def _signing_key(token: str, jwks: dict[str, Any]) -> Any:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise TokenError(str(exc)) from exc
    # Pin the algorithm: never accept ``none`` or an HMAC token signed with the
    # (public) RSA key material.
    if header.get("alg") != "RS256":
        raise TokenError("unsupported token algorithm")
    kid = header.get("kid")
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return jwt.PyJWK.from_dict(key).key
    raise TokenError("no matching signing key")


def verify_token(
    token: str,
    *,
    jwks: dict[str, Any] | None = None,
    audience: list[str] | None = None,
    issuer: str | None = None,
) -> dict[str, Any]:
    """Return the verified claims, or raise :class:`TokenError`.

    ``jwks``/``audience``/``issuer`` are injectable for tests; production calls
    pass only the token and read the rest from the environment.
    """
    if not token or token.count(".") != 2:
        raise TokenError("malformed token")
    resolved_jwks = jwks if jwks is not None else _fetch_jwks()
    resolved_audience = audience if audience is not None else _audience()
    resolved_issuer = issuer if issuer is not None else _issuer()
    try:
        key = _signing_key(token, resolved_jwks)
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=resolved_audience or None,
            issuer=resolved_issuer or None,
            options={"require": ["exp", "iss", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
