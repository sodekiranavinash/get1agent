"""Minimal OAuth 2.1 client for connecting to remote MCP servers.

Implements the client half of the MCP authorization spec:

1. Protected Resource Metadata discovery (RFC 9728) — path-inserted
   ``/.well-known/oauth-protected-resource`` first, then the host root.
2. Authorization Server Metadata discovery (RFC 8414) — the issuer well-known,
   then the path-inserted variant (this is where GitHub's metadata lives:
   ``https://github.com/.well-known/oauth-authorization-server/login/oauth``).
3. Client registration — pre-registered credentials (from the catalog), then
   Client ID Metadata Documents (CIMD), then Dynamic Client Registration
   (RFC 7591). GitHub supports none of the dynamic flows, so it is catalog
   pre-registered.
4. Authorization Code + PKCE (S256) with a Resource Indicator (RFC 8707).
5. Token exchange and refresh-token rotation.

Only the standard library is used, matching the ``web-search`` tool's approach.
Callers own token storage; this module never persists anything.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_TIMEOUT = 20

# Fallback scopes when neither the PRM nor the catalog specifies any.
DEFAULT_SCOPE_FALLBACK: list[str] = []


class OAuthError(Exception):
    """An OAuth discovery, registration or token step failed."""

    def __init__(
        self,
        error: str,
        description: str | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(description or error)
        self.error = error
        self.description = description
        self.status = status


# --- HTTP --------------------------------------------------------------------


def _request(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Accept", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OAuthError("network_error", str(exc)) from exc


def _get_json(url: str, timeout: int) -> tuple[int, Any]:
    status, _, body = _request(url, timeout=timeout)
    if status >= 400 or not body:
        return status, None
    try:
        return status, json.loads(body)
    except ValueError:
        return status, None


def _post_form(
    url: str, form: dict[str, str], *, timeout: int
) -> tuple[int, dict[str, str], bytes]:
    body = urllib.parse.urlencode(form).encode("utf-8")
    return _request(
        url,
        method="POST",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        timeout=timeout,
    )


def _post_json(
    url: str, payload: dict[str, Any], *, timeout: int
) -> tuple[int, dict[str, str], bytes]:
    body = json.dumps(payload).encode("utf-8")
    return _request(
        url,
        method="POST",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=timeout,
    )


def _origin(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _well_known(base: str, suffix: str) -> str:
    return base.rstrip("/") + suffix


# --- discovery ---------------------------------------------------------------


def discover_protected_resource(server_url: str, *, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any] | None:
    """Fetch RFC 9728 Protected Resource Metadata for an MCP server URL."""
    parsed = urllib.parse.urlsplit(server_url)
    path = parsed.path or ""
    candidates = [
        # Path-inserted form: /.well-known/oauth-protected-resource/<path>
        f"{_origin(server_url)}/.well-known/oauth-protected-resource{path}",
        # Host-root form.
        f"{_origin(server_url)}/.well-known/oauth-protected-resource",
    ]
    for candidate in dict.fromkeys(candidates):
        _, payload = _get_json(candidate, timeout)
        if isinstance(payload, dict) and payload.get("authorization_servers"):
            return payload
    return None


def discover_authorization_server(issuer: str, *, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any] | None:
    """Fetch RFC 8414 / OIDC Authorization Server Metadata for an issuer."""
    parsed = urllib.parse.urlsplit(issuer)
    path = parsed.path or ""
    origin = _origin(issuer)
    candidates = [
        f"{issuer.rstrip('/')}/.well-known/oauth-authorization-server",
        f"{origin}/.well-known/oauth-authorization-server{path}",
        f"{issuer.rstrip('/')}/.well-known/openid-configuration",
        f"{origin}/.well-known/openid-configuration{path}",
    ]
    for candidate in dict.fromkeys(candidates):
        _, payload = _get_json(candidate, timeout)
        if isinstance(payload, dict) and payload.get("authorization_endpoint"):
            return payload
    return None


def _normalize_metadata(
    *,
    server_url: str,
    protected: dict[str, Any] | None,
    server: dict[str, Any] | None,
    override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    override = override or {}
    protected = protected or {}
    server = server or {}

    resource = override.get("resource") or protected.get("resource") or server_url
    authorization_endpoint = override.get("authorization_endpoint") or server.get(
        "authorization_endpoint"
    )
    token_endpoint = override.get("token_endpoint") or server.get("token_endpoint")
    if not authorization_endpoint or not token_endpoint:
        raise OAuthError(
            "discovery_failed",
            "could not determine the authorization or token endpoint",
        )

    scopes = (
        override.get("scopes")
        or protected.get("scopes_supported")
        or server.get("scopes_supported")
        or []
    )
    return {
        "resource": resource,
        "issuer": server.get("issuer") or override.get("issuer"),
        "authorization_endpoint": authorization_endpoint,
        "token_endpoint": token_endpoint,
        "registration_endpoint": override.get("registration_endpoint")
        or server.get("registration_endpoint"),
        "scopes_supported": list(scopes),
        "code_challenge_methods_supported": server.get(
            "code_challenge_methods_supported", ["S256"]
        ),
    }


def discover(
    server_url: str,
    *,
    override: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Resolve the OAuth metadata needed to authorize against ``server_url``.

    ``override`` (from the public catalog) short-circuits discovery for
    providers that do not expose standard metadata.
    """
    override = override or {}
    if override.get("authorization_endpoint") and override.get("token_endpoint"):
        return _normalize_metadata(server_url=server_url, protected=None, server=None, override=override)

    protected = discover_protected_resource(server_url, timeout=timeout)
    servers = (protected or {}).get("authorization_servers") or []
    issuer = override.get("issuer") or (servers[0] if servers else None)

    server = None
    if issuer:
        server = discover_authorization_server(issuer, timeout=timeout)
    if server is None and override.get("issuer"):
        # Catalog-declared issuer that lacks well-known metadata.
        server = {}

    return _normalize_metadata(
        server_url=server_url, protected=protected, server=server, override=override
    )


# --- client registration -----------------------------------------------------


def register_client(
    registration_endpoint: str,
    *,
    redirect_uri: str,
    client_name: str,
    scopes: list[str],
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """RFC 7591 Dynamic Client Registration. Returns ``client_id``/``client_secret``."""
    payload = {
        "client_name": client_name,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": " ".join(scopes),
    }
    status, _, body = _post_json(registration_endpoint, payload, timeout=timeout)
    if status >= 400:
        raise OAuthError("registration_failed", _error_detail(body), status)
    try:
        registered = json.loads(body or b"{}")
    except ValueError as exc:
        raise OAuthError("registration_failed", "invalid registration response") from exc
    client_id = registered.get("client_id")
    if not client_id:
        raise OAuthError("registration_failed", "registration returned no client_id")
    return {
        "client_id": client_id,
        "client_secret": registered.get("client_secret"),
        "registration_method": "dcr",
    }


# --- PKCE / authorization ----------------------------------------------------


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def new_state() -> str:
    return secrets.token_urlsafe(32)


def build_authorization_url(
    authorization_endpoint: str,
    *,
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    state: str,
    code_challenge: str,
    resource: str | None = None,
) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if scopes:
        params["scope"] = " ".join(scopes)
    if resource:
        params["resource"] = resource
    separator = "&" if "?" in authorization_endpoint else "?"
    return f"{authorization_endpoint}{separator}{urllib.parse.urlencode(params)}"


# --- token endpoint ----------------------------------------------------------


def _error_detail(body: bytes) -> str | None:
    if not body:
        return None
    try:
        parsed = json.loads(body)
    except ValueError:
        return body[:300].decode("utf-8", "replace")
    if isinstance(parsed, dict):
        return str(parsed.get("error_description") or parsed.get("error") or "")[:300] or None
    return None


def _parse_token_response(body: bytes) -> dict[str, Any]:
    """Accept both JSON and form-encoded token responses (GitHub does both)."""
    if not body:
        raise OAuthError("token_response_invalid", "empty token response")
    try:
        parsed: Any = json.loads(body)
    except ValueError:
        parsed = dict(urllib.parse.parse_qsl(body.decode("utf-8", "replace")))
    if not isinstance(parsed, dict) or not parsed.get("access_token"):
        raise OAuthError(
            "token_response_invalid",
            str(parsed.get("error_description") or parsed.get("error") or "no access_token"),
        )
    expires_in = parsed.get("expires_in")
    try:
        expires_in = int(expires_in) if expires_in is not None else None
    except (TypeError, ValueError):
        expires_in = None
    scope = parsed.get("scope")
    return {
        "access_token": parsed["access_token"],
        "refresh_token": parsed.get("refresh_token"),
        "token_type": parsed.get("token_type") or "Bearer",
        "expires_in": expires_in,
        "scope": scope.split() if isinstance(scope, str) else scope,
    }


def _token_request(
    token_endpoint: str,
    form: dict[str, str],
    *,
    client_id: str,
    client_secret: str | None,
    timeout: int,
) -> dict[str, Any]:
    body = {"client_id": client_id, **form}
    if client_secret:
        # GitHub (and most confidential clients) accept the secret in the body.
        body["client_secret"] = client_secret
    status, _, raw = _post_form(token_endpoint, body, timeout=timeout)
    if status >= 400:
        raise OAuthError(
            "token_request_failed", _error_detail(raw), status
        )
    return _parse_token_response(raw)


def exchange_code(
    token_endpoint: str,
    *,
    code: str,
    redirect_uri: str,
    client_id: str,
    code_verifier: str,
    client_secret: str | None = None,
    resource: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    if resource:
        form["resource"] = resource
    return _token_request(
        token_endpoint,
        form,
        client_id=client_id,
        client_secret=client_secret,
        timeout=timeout,
    )


def refresh_access_token(
    token_endpoint: str,
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str | None = None,
    resource: str | None = None,
    scopes: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    form = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    if resource:
        form["resource"] = resource
    if scopes:
        form["scope"] = " ".join(scopes)
    return _token_request(
        token_endpoint,
        form,
        client_id=client_id,
        client_secret=client_secret,
        timeout=timeout,
    )
