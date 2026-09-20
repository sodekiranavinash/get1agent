"""Remote MCP connection orchestration.

Owns the lifecycle of a user's connection to a remote (Streamable HTTP) MCP
server: OAuth discovery + authorization, encrypted token storage, lazy refresh
with rotation-safe writes, and tool listing/invocation.

The public catalog lives in :mod:`src.catalog`; HTTP transport in
:mod:`core.mcp_http`; OAuth in :mod:`core.oauth`; token encryption in
:mod:`core.crypto`.
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Any
from urllib.parse import urlparse

from core import crypto, mcp_http, oauth
from core.storage import Storage
from data.client import now_epoch, now_iso
from data.repositories import mcp_connections as repo
from data.repositories.mcp_connections import (
    STATUS_CONNECTED,
    STATUS_ERROR,
    STATUS_PENDING,
    STATUS_REAUTH_REQUIRED,
    ConnectionNotFound,
    RefreshConflict,
)

from . import catalog, registry

MAX_CONNECTIONS_PER_USER = 20
CONNECT_TIMEOUT_SECONDS = 15
TOOL_TIMEOUT_SECONDS = 30
# Refresh this many seconds before the access token actually expires.
REFRESH_SKEW_SECONDS = 60

_FIELD_ACCESS = "accessToken"
_FIELD_REFRESH = "refreshToken"
_FIELD_CLIENT = "clientSecret"

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# --- helpers -----------------------------------------------------------------


def _redirect_uri() -> str:
    value = os.environ.get("MCP_OAUTH_REDIRECT_URI", "").strip()
    if not value:
        raise ApiError(500, "MCP_OAUTH_REDIRECT_URI is not configured")
    return value


def _frontend_url() -> str:
    return os.environ.get("FRONTEND_URL", "").rstrip("/")


def _validate_server_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ApiError(400, "Server URL is required")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ApiError(400, "Enter a valid server URL")
    if parsed.scheme != "https" and parsed.hostname not in _LOCAL_HOSTS:
        raise ApiError(400, "Server URL must use HTTPS")
    return value


def _encrypt(user_id: str, conn_id: str, field: str, value: str | None) -> str | None:
    if value is None:
        return None
    return crypto.encrypt(value, context=crypto.connection_context(user_id, conn_id, field))


def _decrypt(user_id: str, conn_id: str, field: str, value: str | None) -> str | None:
    if not value:
        return None
    try:
        return crypto.decrypt(value, context=crypto.connection_context(user_id, conn_id, field))
    except crypto.CryptoError as exc:
        raise ApiError(409, "Stored credentials could not be read; reconnect required") from exc


def _tools_key(user_id: str, conn_id: str) -> str:
    return f"mcp/{user_id}/{conn_id}/tools.json"


def _cache_tools(user_id: str, conn_id: str, tools: list[dict[str, Any]]) -> None:
    try:
        Storage().put_json(_tools_key(user_id, conn_id), {"tools": tools, "updatedAt": now_iso()})
    except Exception:  # noqa: BLE001 - cache is best-effort
        pass


def load_cached_tools(user_id: str, conn_id: str) -> list[dict[str, Any]]:
    try:
        cached = Storage().get_json(_tools_key(user_id, conn_id))
    except Exception:  # noqa: BLE001
        return []
    if isinstance(cached, dict) and isinstance(cached.get("tools"), list):
        return [tool for tool in cached["tools"] if isinstance(tool, dict)]
    return []


def serialize(connection: dict[str, Any]) -> dict[str, Any]:
    """Public shape — never exposes token fields."""
    return {
        "id": connection.get("connId"),
        "name": connection.get("name"),
        "description": connection.get("description"),
        "serverUrl": connection.get("serverUrl"),
        "transport": connection.get("transport", "streamable-http"),
        "authType": connection.get("authType"),
        "catalogId": connection.get("catalogId"),
        "status": connection.get("status"),
        "enabled": connection.get("enabled", True) is not False,
        "toolCount": int(connection.get("toolCount") or 0),
        "lastError": connection.get("lastError"),
        "lastRefreshedAt": connection.get("lastRefreshedAt"),
        "createdAt": connection.get("createdAt"),
        "updatedAt": connection.get("updatedAt"),
    }


def _require(user_id: str, conn_id: str) -> dict[str, Any]:
    try:
        conn_id = str(uuid.UUID(conn_id))
    except (ValueError, TypeError) as exc:
        raise ApiError(404, "Connection not found") from exc
    connection = repo.get_connection(user_id, conn_id)
    if connection is None:
        raise ApiError(404, "Connection not found")
    return connection


def _disabled_tools(connection: dict[str, Any]) -> set[str]:
    return {str(name) for name in connection.get("disabledTools") or []}


# --- listing -----------------------------------------------------------------


def list_connections(user_id: str) -> list[dict[str, Any]]:
    return [serialize(item) for item in repo.list_connections(user_id)]


def get_connection(user_id: str, conn_id: str) -> dict[str, Any]:
    return serialize(_require(user_id, conn_id))


def public_catalog() -> list[dict[str, Any]]:
    return catalog.public_entries()


def search_registry(query: dict[str, str]) -> dict[str, Any]:
    return registry.search_registry(query)


# --- connect -----------------------------------------------------------------


def _probe_auth(server_url: str) -> str:
    """Return ``none`` when the server answers without a token, else ``oauth``."""
    try:
        mcp_http.list_tools(server_url, timeout=CONNECT_TIMEOUT_SECONDS)
        return "none"
    except mcp_http.RemoteMcpAuthError:
        return "oauth"
    except mcp_http.RemoteMcpError as exc:
        raise ApiError(400, f"Could not reach the MCP server: {exc}") from exc


def _existing_urls(user_id: str) -> dict[str, dict[str, Any]]:
    return {item.get("serverUrl"): item for item in repo.list_connections(user_id)}


def start_connection(user_id: str, body: dict[str, Any]) -> dict[str, Any]:
    catalog_id = (body.get("catalogId") or "").strip() or None
    entry = catalog.get_entry(catalog_id) if catalog_id else None
    if catalog_id and entry is None:
        raise ApiError(400, "Unknown catalog server")

    if entry is not None:
        name = str(entry.get("name") or "").strip()
        description = str(entry.get("description") or "").strip()
        server_url = _validate_server_url(str(entry.get("serverUrl") or ""))
    else:
        name = str(body.get("name") or "").strip()
        if not name:
            raise ApiError(400, "Give the server a name")
        description = str(body.get("description") or "").strip()
        server_url = _validate_server_url(str(body.get("url") or ""))

    if repo.count_connections(user_id) >= MAX_CONNECTIONS_PER_USER:
        raise ApiError(429, f"At most {MAX_CONNECTIONS_PER_USER} MCP servers per account")

    current = _existing_urls(user_id).get(server_url)
    if current is not None:
        if current.get("status") == STATUS_CONNECTED:
            raise ApiError(409, "This server is already connected")
        # A previous attempt is still pending or failed: restart authorization
        # rather than leaving the user stuck with an unusable connection.
        if current.get("authType") == "oauth":
            return reauthorize(user_id, current["connId"])
        raise ApiError(409, "This server is already connected")

    conn_id = str(uuid.uuid4())

    auth_type = (entry.get("auth") or {}).get("type") if entry else None
    if auth_type is None:
        auth_type = _probe_auth(server_url)

    if auth_type == "none":
        repo.create_connection(
            user_id, conn_id, name=name, server_url=server_url,
            auth_type="none", catalog_id=catalog_id, description=description,
        )
        _finish_connected(user_id, conn_id)
        return {"connection": get_connection(user_id, conn_id), "authorizationUrl": None}

    if auth_type == "apikey":
        repo.create_connection(
            user_id, conn_id, name=name, server_url=server_url,
            auth_type="apikey", catalog_id=catalog_id, description=description,
        )
        return {"connection": get_connection(user_id, conn_id), "authorizationUrl": None}

    # OAuth.
    override = catalog.oauth_override(entry)
    try:
        metadata = oauth.discover(server_url, override=override, timeout=CONNECT_TIMEOUT_SECONDS)
    except oauth.OAuthError as exc:
        raise ApiError(400, f"OAuth discovery failed: {exc.description or exc.error}") from exc

    scopes = list(metadata.get("scopes_supported") or [])
    client_id, client_secret = catalog.client_credentials(entry)
    registration_method = "pre" if client_id else "dcr"
    if not client_id and metadata.get("registration_endpoint"):
        try:
            registered = oauth.register_client(
                metadata["registration_endpoint"],
                redirect_uri=_redirect_uri(),
                client_name="get1agent",
                scopes=scopes,
                timeout=CONNECT_TIMEOUT_SECONDS,
            )
        except oauth.OAuthError as exc:
            raise ApiError(400, f"Client registration failed: {exc.description or exc.error}") from exc
        client_id = registered["client_id"]
        client_secret = registered.get("client_secret")
    if not client_id:
        raise ApiError(
            400,
            "This server requires a pre-registered OAuth client that is not configured",
        )

    repo.create_connection(
        user_id, conn_id, name=name, server_url=server_url,
        auth_type="oauth", catalog_id=catalog_id, scopes=scopes,
        description=description,
    )
    repo.save_client(
        user_id, conn_id,
        client_id=client_id,
        client_secret_enc=_encrypt(user_id, conn_id, _FIELD_CLIENT, client_secret),
        issuer=metadata.get("issuer"),
        authorization_server=metadata.get("issuer"),
        authorization_endpoint=metadata.get("authorization_endpoint"),
        token_endpoint=metadata.get("token_endpoint"),
        resource=metadata.get("resource"),
        registration_method=registration_method,
    )

    verifier, challenge = oauth.pkce_pair()
    state = f"{user_id}.{oauth.new_state()}"
    state_payload: dict[str, Any] = {
        "connId": conn_id,
        "codeVerifier": verifier,
        "redirectUri": _redirect_uri(),
        "clientId": client_id,
        "tokenEndpoint": metadata.get("token_endpoint"),
        "resource": metadata.get("resource"),
        "serverUrl": server_url,
        "scopes": scopes,
    }
    secret_enc = _encrypt(user_id, conn_id, _FIELD_CLIENT, client_secret)
    if secret_enc:
        state_payload["clientSecretEnc"] = secret_enc
    repo.create_state(user_id, state, **state_payload)

    authorization_url = oauth.build_authorization_url(
        metadata["authorization_endpoint"],
        client_id=client_id,
        redirect_uri=_redirect_uri(),
        scopes=scopes,
        state=state,
        code_challenge=challenge,
        resource=metadata.get("resource"),
    )
    return {"connection": get_connection(user_id, conn_id), "authorizationUrl": authorization_url}


def _finish_connected(user_id: str, conn_id: str) -> None:
    try:
        tools = list_connection_tools(user_id, conn_id)
        repo.set_status(user_id, conn_id, STATUS_CONNECTED, tool_count=len(tools))
    except Exception as exc:  # noqa: BLE001
        message = exc.message if isinstance(exc, ApiError) else str(exc)
        repo.set_status(user_id, conn_id, STATUS_ERROR, error=message[:300])


# --- OAuth callback ----------------------------------------------------------


def _callback_redirect(**params: str) -> dict[str, Any]:
    base = _frontend_url()
    query = "&".join(f"{key}={value}" for key, value in params.items() if value is not None)
    location = f"{base}/mcp/callback?{query}" if base else f"/mcp/callback?{query}"
    return {"statusCode": 302, "headers": {"location": location}, "body": ""}


def _parse_state(state: str) -> tuple[str, str]:
    user_id, _, token = (state or "").partition(".")
    if not user_id.startswith("u_") or not token:
        raise ApiError(400, "Invalid OAuth state")
    return user_id, state


def handle_callback(query: dict[str, str]) -> dict[str, Any]:
    state = query.get("state") or ""
    if not state:
        return _callback_redirect(status="error", message="missing_state")
    try:
        user_id, full_state = _parse_state(state)
    except ApiError:
        return _callback_redirect(status="error", message="invalid_state")

    payload = repo.consume_state(user_id, full_state)
    if payload is None:
        return _callback_redirect(status="error", message="state_expired")

    conn_id = str(payload.get("connId") or "")

    error = query.get("error")
    if error:
        if conn_id:
            repo.set_status(user_id, conn_id, STATUS_REAUTH_REQUIRED, error=query.get("error_description") or error)
        return _callback_redirect(status="error", message=error)

    code = query.get("code") or ""
    if not code:
        return _callback_redirect(status="error", message="missing_code")

    try:
        client_secret = _decrypt(user_id, conn_id, _FIELD_CLIENT, payload.get("clientSecretEnc"))
        tokens = oauth.exchange_code(
            payload["tokenEndpoint"],
            code=code,
            redirect_uri=payload.get("redirectUri") or _redirect_uri(),
            client_id=payload["clientId"],
            code_verifier=payload["codeVerifier"],
            client_secret=client_secret,
            resource=payload.get("resource"),
            timeout=CONNECT_TIMEOUT_SECONDS,
        )
    except (oauth.OAuthError, ApiError) as exc:
        if conn_id:
            repo.set_status(user_id, conn_id, STATUS_ERROR, error=str(exc)[:300])
        return _callback_redirect(status="error", message="token_exchange_failed")

    _store_tokens(user_id, conn_id, tokens)
    try:
        tools = list_connection_tools(user_id, conn_id)
        repo.set_status(user_id, conn_id, STATUS_CONNECTED, tool_count=len(tools))
    except ApiError as exc:
        repo.set_status(user_id, conn_id, STATUS_ERROR, error=exc.message)
    return _callback_redirect(status="connected", connection=conn_id)


# --- tokens ------------------------------------------------------------------


def _expiry(tokens: dict[str, Any]) -> int | None:
    expires_in = tokens.get("expires_in")
    if not expires_in:
        return None
    return now_epoch() + int(expires_in)


def _store_tokens(
    user_id: str,
    conn_id: str,
    tokens: dict[str, Any],
    *,
    expected_refresh_enc: Any = repo.UNSET,
) -> None:
    repo.save_tokens(
        user_id,
        conn_id,
        access_token_enc=crypto.encrypt(
            tokens["access_token"], context=crypto.connection_context(user_id, conn_id, _FIELD_ACCESS)
        ),
        refresh_token_enc=_encrypt(user_id, conn_id, _FIELD_REFRESH, tokens.get("refresh_token")),
        token_type=tokens.get("token_type") or "Bearer",
        token_expires_at=_expiry(tokens),
        expected_refresh_enc=expected_refresh_enc,
    )


def _refresh(user_id: str, connection: dict[str, Any], *, attempt: int = 0) -> None:
    conn_id = connection["connId"]
    current_refresh_enc = connection.get("refreshTokenEnc")
    refresh_plain = _decrypt(user_id, conn_id, _FIELD_REFRESH, current_refresh_enc)
    if not refresh_plain:
        repo.set_status(user_id, conn_id, STATUS_REAUTH_REQUIRED, error="no refresh token")
        raise ApiError(409, "Reconnect required: the provider issued no refresh token")

    token_endpoint = connection.get("tokenEndpoint")
    client_id = connection.get("clientId")
    if not token_endpoint or not client_id:
        repo.set_status(user_id, conn_id, STATUS_REAUTH_REQUIRED, error="missing client metadata")
        raise ApiError(409, "Reconnect required")

    client_secret = _decrypt(user_id, conn_id, _FIELD_CLIENT, connection.get("clientSecretEnc"))
    try:
        tokens = oauth.refresh_access_token(
            token_endpoint,
            refresh_token=refresh_plain,
            client_id=client_id,
            client_secret=client_secret,
            resource=connection.get("resource"),
            scopes=connection.get("scopes"),
            timeout=CONNECT_TIMEOUT_SECONDS,
        )
    except oauth.OAuthError as exc:
        # Providers that rotate refresh tokens (GitHub with expiring tokens)
        # invalidate the old one. If another worker already rotated it, our
        # stored token has changed — retry once with the winner's token rather
        # than wrongly forcing the user to reconnect.
        if attempt == 0:
            fresh = repo.get_connection(user_id, conn_id)
            if (
                fresh is not None
                and fresh.get("refreshTokenEnc")
                and fresh["refreshTokenEnc"] != current_refresh_enc
            ):
                return _refresh(user_id, fresh, attempt=1)
        repo.set_status(
            user_id, conn_id, STATUS_REAUTH_REQUIRED, error=str(exc.description or exc.error)[:300]
        )
        raise ApiError(409, "Reconnect required: authorization expired or was revoked") from exc

    try:
        _store_tokens(
            user_id, conn_id, tokens, expected_refresh_enc=current_refresh_enc
        )
    except RefreshConflict:
        # Another worker rotated first; keep its token and move on.
        pass


def access_token(user_id: str, connection: dict[str, Any]) -> str:
    conn_id = connection["connId"]
    expires_at = connection.get("tokenExpiresAt")
    if connection.get("accessTokenEnc") and (
        not expires_at or now_epoch() < int(expires_at) - REFRESH_SKEW_SECONDS
    ):
        token = _decrypt(user_id, conn_id, _FIELD_ACCESS, connection["accessTokenEnc"])
        if token:
            return token
    _refresh(user_id, connection)
    fresh = repo.get_connection(user_id, conn_id)
    if fresh is None:
        raise ApiError(404, "Connection not found")
    token = _decrypt(user_id, conn_id, _FIELD_ACCESS, fresh.get("accessTokenEnc"))
    if not token:
        raise ApiError(409, "Reconnect required")
    return token


# --- tools -------------------------------------------------------------------


def _uses_token(connection: dict[str, Any]) -> bool:
    return connection.get("authType") in ("oauth", "apikey")


def _token_for(user_id: str, connection: dict[str, Any]) -> str | None:
    return access_token(user_id, connection) if _uses_token(connection) else None


def _retry_after_auth_error(user_id: str, connection: dict[str, Any]) -> dict[str, Any]:
    """Recover from a rejected token: refresh OAuth, or fail for API keys."""
    if connection.get("authType") == "oauth":
        _refresh(user_id, connection)
        return _require(user_id, connection["connId"])
    repo.set_status(user_id, connection["connId"], STATUS_ERROR, error="credentials rejected")
    raise ApiError(409, "Credentials were rejected by the server")


def list_connection_tools(user_id: str, conn_id: str) -> list[dict[str, Any]]:
    connection = _require(user_id, conn_id)
    token = _token_for(user_id, connection)
    try:
        tools = mcp_http.list_tools(connection["serverUrl"], access_token=token, timeout=TOOL_TIMEOUT_SECONDS)
    except mcp_http.RemoteMcpAuthError:
        fresh = _retry_after_auth_error(user_id, connection)
        tools = mcp_http.list_tools(
            fresh["serverUrl"], access_token=_token_for(user_id, fresh), timeout=TOOL_TIMEOUT_SECONDS
        )
    except mcp_http.RemoteMcpError as exc:
        repo.set_status(user_id, conn_id, STATUS_ERROR, error=str(exc)[:300])
        raise ApiError(502, f"Remote MCP server error: {exc}") from exc
    _cache_tools(user_id, conn_id, tools)
    return tools


def list_tools_public(user_id: str, conn_id: str) -> list[dict[str, Any]]:
    """Tool list for the UI, each flagged with its enabled state.

    Served from the cached schemas so opening a dialog does not re-hit the
    remote server; the cache is populated on the first fetch (and reconnecting
    the server refreshes it).
    """
    connection = _require(user_id, conn_id)
    disabled = _disabled_tools(connection)
    tools = load_cached_tools(user_id, conn_id)
    if not tools:
        tools = list_connection_tools(user_id, conn_id)
    return [
        {
            "name": tool.get("name"),
            "description": tool.get("description"),
            "inputSchema": tool.get("inputSchema"),
            "enabled": str(tool.get("name") or "") not in disabled,
        }
        for tool in tools
    ]


def call_connection_tool(
    user_id: str, conn_id: str, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    connection = _require(user_id, conn_id)
    token = _token_for(user_id, connection)
    try:
        return mcp_http.call_tool(
            connection["serverUrl"], name, arguments,
            access_token=token, timeout=TOOL_TIMEOUT_SECONDS,
        )
    except mcp_http.RemoteMcpAuthError:
        fresh = _retry_after_auth_error(user_id, connection)
        return mcp_http.call_tool(
            fresh["serverUrl"], name, arguments,
            access_token=_token_for(user_id, fresh), timeout=TOOL_TIMEOUT_SECONDS,
        )


def set_api_key(user_id: str, conn_id: str, token: str) -> dict[str, Any]:
    connection = _require(user_id, conn_id)
    if connection.get("authType") != "apikey":
        raise ApiError(400, "This connection does not use an API key")
    token = (token or "").strip()
    if not token:
        raise ApiError(400, "API key is required")
    repo.save_tokens(
        user_id,
        conn_id,
        access_token_enc=crypto.encrypt(
            token, context=crypto.connection_context(user_id, conn_id, _FIELD_ACCESS)
        ),
        token_type="Bearer",
    )
    _finish_connected(user_id, conn_id)
    return get_connection(user_id, conn_id)


def refresh_connection(user_id: str, conn_id: str) -> dict[str, Any]:
    connection = _require(user_id, conn_id)
    if not connection.get("refreshTokenEnc"):
        raise ApiError(409, "Reconnect required: the provider issued no refresh token")
    _refresh(user_id, connection)
    return get_connection(user_id, conn_id)


def set_enabled(user_id: str, conn_id: str, enabled: Any) -> dict[str, Any]:
    """Enable/disable a connection without disconnecting it."""
    _require(user_id, conn_id)
    if not isinstance(enabled, bool):
        raise ApiError(400, "enabled must be a boolean")
    repo.set_enabled(user_id, conn_id, enabled)
    return get_connection(user_id, conn_id)


def set_tool_enabled(
    user_id: str, conn_id: str, name: Any, enabled: Any
) -> dict[str, Any]:
    """Enable/disable a single tool on a connection."""
    _require(user_id, conn_id)
    tool_name = str(name or "").strip()
    if not tool_name:
        raise ApiError(400, "Tool name is required")
    if not isinstance(enabled, bool):
        raise ApiError(400, "enabled must be a boolean")
    repo.set_tool_enabled(user_id, conn_id, tool_name, enabled)
    return get_connection(user_id, conn_id)


def reauthorize(user_id: str, conn_id: str) -> dict[str, Any]:
    """Restart OAuth for an existing connection (expired/revoked grant)."""
    connection = _require(user_id, conn_id)
    if connection.get("authType") != "oauth":
        raise ApiError(400, "This connection does not use OAuth")
    authorization_endpoint = connection.get("authorizationEndpoint")
    client_id = connection.get("clientId")
    if not authorization_endpoint or not client_id:
        raise ApiError(409, "Remove and re-add this server to reconnect")

    scopes = list(connection.get("scopes") or [])
    verifier, challenge = oauth.pkce_pair()
    state = f"{user_id}.{oauth.new_state()}"
    payload: dict[str, Any] = {
        "connId": conn_id,
        "codeVerifier": verifier,
        "redirectUri": _redirect_uri(),
        "clientId": client_id,
        "tokenEndpoint": connection.get("tokenEndpoint"),
        "resource": connection.get("resource"),
        "serverUrl": connection.get("serverUrl"),
        "scopes": scopes,
    }
    if connection.get("clientSecretEnc"):
        payload["clientSecretEnc"] = connection["clientSecretEnc"]
    repo.create_state(user_id, state, **payload)
    repo.set_status(user_id, conn_id, STATUS_PENDING)

    authorization_url = oauth.build_authorization_url(
        authorization_endpoint,
        client_id=client_id,
        redirect_uri=_redirect_uri(),
        scopes=scopes,
        state=state,
        code_challenge=challenge,
        resource=connection.get("resource"),
    )
    return {"connection": get_connection(user_id, conn_id), "authorizationUrl": authorization_url}


def disconnect(user_id: str, conn_id: str) -> None:
    connection = _require(user_id, conn_id)
    try:
        Storage().delete(_tools_key(user_id, connection["connId"]))
    except Exception:  # noqa: BLE001
        pass
    repo.delete_connection(user_id, connection["connId"])


def _sanitize_tool_name(value: str) -> str:
    return re.sub(r"[^a-z0-9._/-]", "-", value.lower())[:120]
