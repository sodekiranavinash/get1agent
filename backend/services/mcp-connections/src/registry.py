"""Live discovery of remote MCP servers from the official MCP Registry.

The registry (``registry.modelcontextprotocol.io``) is public and
unauthenticated. We proxy it so the SPA avoids CORS and so we can keep only
the servers this service can actually connect to: remote ``streamable-http``
endpoints that do **not** require a caller-supplied header credential.

OAuth is not labelled by the registry — the connection flow probes it
(``service._probe_auth`` / ``core.oauth.discover``) when the user connects.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from core import mcp_http

REGISTRY_BASE = os.environ.get(
    "MCP_REGISTRY_URL", "https://registry.modelcontextprotocol.io"
).rstrip("/")
REGISTRY_TIMEOUT_SECONDS = int(os.environ.get("MCP_REGISTRY_TIMEOUT_SECONDS", "10"))
REGISTRY_CACHE_TTL_SECONDS = int(os.environ.get("MCP_REGISTRY_CACHE_TTL_SECONDS", "600"))
AUTH_PROBE_TIMEOUT_SECONDS = int(os.environ.get("MCP_REGISTRY_PROBE_TIMEOUT_SECONDS", "4"))
DEFAULT_LIMIT = 30
MAX_LIMIT = 100

# Per-container cache so repeated searches do not hammer the public registry.
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
# Per-server-URL auth classification cache (probing is the expensive part).
_auth_cache: dict[str, tuple[float, str]] = {}


def _fetch(params: dict[str, str]) -> dict[str, Any]:
    url = f"{REGISTRY_BASE}/v0.1/servers?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "get1agent"},
    )
    with urllib.request.urlopen(request, timeout=REGISTRY_TIMEOUT_SECONDS) as response:
        return json.loads(response.read() or b"{}")


def _has_required_header(remote: dict[str, Any]) -> bool:
    headers = remote.get("headers") or []
    return any(
        isinstance(header, dict) and header.get("isRequired") for header in headers
    )


def _remote_url(server: dict[str, Any]) -> str | None:
    """First usable remote endpoint (Streamable HTTP, no required headers)."""
    for remote in server.get("remotes") or []:
        if not isinstance(remote, dict):
            continue
        if remote.get("type") != "streamable-http":
            continue
        url = str(remote.get("url") or "").strip()
        if not url or _has_required_header(remote):
            continue
        return url
    return None


def _category(server: dict[str, Any]) -> str | None:
    meta = server.get("_meta") or {}
    publisher = meta.get("io.modelcontextprotocol.registry/publisher-provided")
    if isinstance(publisher, dict):
        categories = publisher.get("categories")
        if isinstance(categories, list) and categories:
            return str(categories[0])
    return None


def _map_server(server: dict[str, Any]) -> dict[str, Any] | None:
    server_url = _remote_url(server)
    if not server_url:
        return None
    name = str(server.get("title") or server.get("name") or "").strip()
    if not name:
        return None
    repository = server.get("repository") or {}
    docs_url = server.get("websiteUrl") or (
        repository.get("url") if isinstance(repository, dict) else None
    )
    return {
        "id": str(server.get("name") or server_url),
        "name": name,
        "description": str(server.get("description") or ""),
        "category": _category(server),
        "source": "public",
        "docsUrl": docs_url or None,
        "serverUrl": server_url,
        "transport": "streamable-http",
    }


def _params(query: dict[str, str]) -> dict[str, str]:
    try:
        limit = int(query.get("limit") or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(limit, MAX_LIMIT))
    params: dict[str, str] = {"limit": str(limit), "version": "latest"}
    search = (query.get("search") or "").strip()
    if search:
        params["search"] = search
    cursor = (query.get("cursor") or "").strip()
    if cursor:
        params["cursor"] = cursor
    return params


def _probe_auth(server_url: str) -> str:
    """Best-effort auth classification: ``oauth`` or ``none`` (else ``unknown``)."""
    try:
        mcp_http.list_tools(server_url, timeout=AUTH_PROBE_TIMEOUT_SECONDS)
        return "none"
    except mcp_http.RemoteMcpAuthError:
        return "oauth"
    except Exception:  # noqa: BLE001 - unreachable/broken servers stay unclassified
        return "unknown"


def _probe_auth_cached(server_url: str, now: float) -> str:
    cached = _auth_cache.get(server_url)
    if cached and now - cached[0] < REGISTRY_CACHE_TTL_SECONDS:
        return cached[1]
    auth = _probe_auth(server_url)
    _auth_cache[server_url] = (now, auth)
    return auth


def _classify_auth(servers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tag each server with ``auth`` (probing uncached URLs concurrently)."""
    if not servers:
        return servers
    now = time.time()
    pending = list(
        dict.fromkeys(
            server["serverUrl"]
            for server in servers
            if not (
                _auth_cache.get(server["serverUrl"])
                and now - _auth_cache[server["serverUrl"]][0] < REGISTRY_CACHE_TTL_SECONDS
            )
        )
    )
    if pending:
        with ThreadPoolExecutor(max_workers=min(len(pending), 24)) as pool:
            results = list(pool.map(_probe_auth, pending))
        stamp = time.time()
        for url, auth in zip(pending, results):
            _auth_cache[url] = (stamp, auth)
    for server in servers:
        cached = _auth_cache.get(server["serverUrl"])
        server["auth"] = cached[1] if cached else "unknown"
    return servers


def _filter_by_auth(
    servers: list[dict[str, Any]], wanted: str
) -> list[dict[str, Any]]:
    """Tag each server with its auth type and keep only ``wanted``."""
    return [server for server in _classify_auth(servers) if server["auth"] == wanted]


def search_registry(query: dict[str, str]) -> dict[str, Any]:
    """Search the official registry and return remote servers we can connect.

    The registry does not publish auth, so every result is classified by a
    best-effort probe (cached per server URL); ``auth`` then keeps only matches.
    """
    params = _params(query)
    auth_filter = (query.get("auth") or "").strip().lower()
    if auth_filter not in ("oauth", "none"):
        auth_filter = ""
    cache_key = urllib.parse.urlencode(
        sorted({**params, "auth": auth_filter}.items())
    )
    cached = _cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < REGISTRY_CACHE_TTL_SECONDS:
        return cached[1]

    try:
        data = _fetch(params)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {"servers": [], "nextCursor": None, "error": str(exc)}

    servers: list[dict[str, Any]] = []
    for item in data.get("servers") or []:
        server = item.get("server") if isinstance(item, dict) else None
        if not isinstance(server, dict):
            continue
        mapped = _map_server(server)
        if mapped:
            servers.append(mapped)

    servers = _classify_auth(servers)
    if auth_filter:
        servers = [server for server in servers if server["auth"] == auth_filter]

    result = {
        "servers": servers,
        "nextCursor": (data.get("metadata") or {}).get("nextCursor"),
    }
    _cache[cache_key] = (now, result)
    return result
