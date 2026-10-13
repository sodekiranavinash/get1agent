"""Verify an Auth0 JWT locally — the one job API Gateway does in production.

In production AI Assistant never verifies a token. The gateway's JWT authorizer
does, and the Lambda reads `requestContext.authorizer.jwt.claims`; `handler.py`
contains no signing or JWKS code at all. That is a feature, and it stays true.

Locally there is no gateway, so *something* has to fill the claims in, and the
tempting shortcuts are both wrong:

* **Trust a `userId` from the request body.** A real authentication bypass, and
  the exact thing the design forbids.
* **Decode the JWT without checking the signature.** Anyone could mint a token for
  any account against a developer's machine, and the code that "works" that way
  trains people to trust an unverified token.

So this module does the check properly, with the standard library only. It is
**local-development code**: `handler.py` never imports it, and `main.py` (the
local ASGI server) is the only caller. Nothing here is reachable from the deployed
Lambda, which is why it may use `urllib` and a module-level cache freely.

Auth0 signs with RS256. Verification is therefore:

1. read the token header → `kid` and `alg`;
2. fetch (and cache) the tenant's JWKS, select the key by `kid`;
3. rebuild the RSA public key from the JWK's `n`/`e`;
4. check the signature, then `iss`, `aud` and `exp`.

The JWKS is cached for an hour and re-fetched when a `kid` is unknown, so key
rotation does not require a restart.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.request
from typing import Any

#: How long a fetched JWKS is trusted before it is fetched again.
JWKS_TTL_SECONDS = 3600
#: Clock skew allowed on `exp`/`iat`, in seconds. Machines drift; tokens do not.
LEEWAY_SECONDS = 60

_jwks_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


class LocalAuthError(Exception):
    """The token could not be verified."""


def _b64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _issuer() -> str:
    issuer = str(os.environ.get("AI_ASSISTANT_AUTH_ISSUER") or "").strip().rstrip("/")
    if issuer:
        return issuer
    domain = str(os.environ.get("VITE_AUTH_DOMAIN") or os.environ.get("AUTH_DOMAIN") or "").strip()
    if not domain:
        raise LocalAuthError(
            "Local token verification needs AI_ASSISTANT_AUTH_ISSUER (or AUTH_DOMAIN)"
        )
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    return domain.rstrip("/")


def _audience() -> str:
    return str(
        os.environ.get("AI_ASSISTANT_AUTH_AUDIENCE") or os.environ.get("AUTH_AUDIENCE") or ""
    ).strip()


def _fetch_json(url: str, timeout: int = 10) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, dict):
        raise LocalAuthError(f"{url} did not return a JSON object")
    return payload


def jwks_url() -> str:
    """The tenant's JWKS endpoint, from the discovery document."""
    explicit = str(os.environ.get("AI_ASSISTANT_AUTH_JWKS_URL") or "").strip()
    if explicit:
        return explicit
    issuer = _issuer()
    document = _fetch_json(f"{issuer}/.well-known/openid-configuration")
    url = str(document.get("jwks_uri") or "").strip()
    if not url:
        raise LocalAuthError("Auth0 discovery document has no jwks_uri")
    return url


def _jwks(force: bool = False) -> list[dict[str, Any]]:
    url = jwks_url()
    cached = _jwks_cache.get(url)
    if not force and cached and time.time() - cached[0] < JWKS_TTL_SECONDS:
        return cached[1]
    document = _fetch_json(url)
    keys = document.get("keys")
    if not isinstance(keys, list) or not keys:
        raise LocalAuthError("JWKS contained no keys")
    _jwks_cache[url] = (time.time(), keys)
    return keys


def _rsa_public_key(jwk: dict[str, Any]):
    """Rebuild an RSA public key from a JWK, using `cryptography` (bundled)."""
    from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: PLC0415

    modulus = int.from_bytes(_b64url(str(jwk["n"])), "big")
    exponent = int.from_bytes(_b64url(str(jwk["e"])), "big")
    return rsa.RSAPublicNumbers(exponent, modulus).public_key()


def _verify_signature(token: str, jwk: dict[str, Any]) -> None:
    from cryptography.exceptions import InvalidSignature  # noqa: PLC0415
    from cryptography.hazmat.primitives import hashes  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric import padding  # noqa: PLC0415

    header_b64, payload_b64, signature_b64 = token.split(".")
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = _b64url(signature_b64)
    try:
        _rsa_public_key(jwk).verify(
            signature, signing_input, padding.PKCS1v15(), hashes.SHA256()
        )
    except InvalidSignature as exc:
        raise LocalAuthError("JWT signature does not verify") from exc


def _select_key(keys: list[dict[str, Any]], kid: str) -> dict[str, Any]:
    for key in keys:
        if str(key.get("kid") or "") == kid:
            return key
    raise LocalAuthError(f"No JWKS key matches kid={kid!r}")


def verify(token: str) -> dict[str, Any]:
    """Verify an Auth0 RS256 token and return its claims, or raise `LocalAuthError`."""
    parts = str(token or "").split(".")
    if len(parts) != 3:
        raise LocalAuthError("Malformed JWT")

    try:
        header = json.loads(_b64url(parts[0]))
        claims = json.loads(_b64url(parts[1]))
    except Exception as exc:  # noqa: BLE001 - any decode failure is a bad token
        raise LocalAuthError("Malformed JWT") from exc
    if not isinstance(header, dict) or not isinstance(claims, dict):
        raise LocalAuthError("Malformed JWT")

    algorithm = str(header.get("alg") or "")
    if algorithm != "RS256":
        # Auth0 issues RS256; accepting `none` or an HMAC algorithm here is the
        # classic JWT confusion vulnerability.
        raise LocalAuthError(f"Unsupported JWT algorithm {algorithm!r}")

    kid = str(header.get("kid") or "")
    if not kid:
        raise LocalAuthError("JWT has no kid")

    try:
        key = _select_key(_jwks(), kid)
    except LocalAuthError:
        # An unknown kid usually means the tenant rotated keys; refetch once.
        key = _select_key(_jwks(force=True), kid)
    _verify_signature(token, key)

    now = int(time.time())
    if int(claims.get("exp") or 0) < now - LEEWAY_SECONDS:
        raise LocalAuthError("JWT has expired")
    if claims.get("iat") and int(claims["iat"]) > now + LEEWAY_SECONDS:
        raise LocalAuthError("JWT is not valid yet")

    expected_issuer = _issuer()
    if str(claims.get("iss") or "").rstrip("/") != expected_issuer:
        raise LocalAuthError("JWT issuer does not match")

    audience = _audience()
    if audience:
        raw_aud = claims.get("aud")
        actual = raw_aud if isinstance(raw_aud, list) else [raw_aud]
        if audience not in [str(item) for item in actual if item is not None]:
            raise LocalAuthError("JWT audience does not match")

    return claims


def fingerprint(claims: dict[str, Any]) -> str:
    """A short, non-reversible id for a token subject — safe to log."""
    subject = str(claims.get("sub") or "")
    return hashlib.sha256(subject.encode("utf-8")).hexdigest()[:12]
