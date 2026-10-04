"""The curated public MCP server catalog.

``catalog.json`` is bundled with the Lambda (it is public, reviewable data) and
served to the SPA so users can connect popular servers in one click. Entries
carry the OAuth discovery overrides needed by providers that do not expose
standard metadata (GitHub), plus the **names** of the environment variables
holding pre-registered client credentials — never the secrets themselves.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "catalog.json")


@lru_cache(maxsize=1)
def load_catalog() -> list[dict[str, Any]]:
    with open(CATALOG_PATH, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    servers = data.get("servers") if isinstance(data, dict) else None
    return [entry for entry in servers or [] if isinstance(entry, dict)]


def get_entry(catalog_id: str) -> dict[str, Any] | None:
    for entry in load_catalog():
        if entry.get("id") == catalog_id:
            return entry
    return None


def public_entries() -> list[dict[str, Any]]:
    """Catalog entries safe to hand to the browser (no credential env names)."""
    entries: list[dict[str, Any]] = []
    for entry in load_catalog():
        auth = entry.get("auth") or {}
        entries.append(
            {
                "id": entry.get("id"),
                "name": entry.get("name"),
                "description": entry.get("description"),
                "category": entry.get("category"),
                "source": entry.get("source", "public"),
                "docsUrl": entry.get("docsUrl"),
                "serverUrl": entry.get("serverUrl"),
                "transport": entry.get("transport", "streamable-http"),
                "authType": auth.get("type", "oauth"),
            }
        )
    return entries


def oauth_override(entry: dict[str, Any] | None) -> dict[str, Any]:
    """Discovery overrides for :func:`core.oauth.discover`."""
    if not entry:
        return {}
    auth = entry.get("auth") or {}
    override: dict[str, Any] = {}
    for key in (
        "issuer",
        "authorizationEndpoint",
        "tokenEndpoint",
        "registrationEndpoint",
        "resource",
    ):
        if auth.get(key):
            target = {
                "authorizationEndpoint": "authorization_endpoint",
                "tokenEndpoint": "token_endpoint",
                "registrationEndpoint": "registration_endpoint",
            }.get(key, key)
            override[target] = auth[key]
    if auth.get("scopes"):
        override["scopes"] = list(auth["scopes"])
    return override


def client_credentials(entry: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Pre-registered client id/secret from the environment, when configured."""
    if not entry:
        return None, None
    auth = entry.get("auth") or {}
    client_id = os.environ.get(auth.get("clientIdEnv") or "", "").strip() or None
    client_secret = os.environ.get(auth.get("clientSecretEnv") or "", "").strip() or None
    return client_id, client_secret
