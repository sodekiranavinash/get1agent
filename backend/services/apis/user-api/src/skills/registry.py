"""Browse the public agent-skills registry (claude-plugins.dev).

No auth. We proxy it so the SPA avoids CORS and so we can classify skills as
prompt-only vs tool-based on demand (that needs the skill body, which the
search index does not return). Results and per-skill classification are cached
in-container.
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

from src.skills.classify import classify_skill
from src.skills.fetch import fetch_text

REGISTRY_BASE = os.environ.get(
    "SKILLS_REGISTRY_URL", "https://api.claude-plugins.dev"
).rstrip("/")
REGISTRY_TIMEOUT_SECONDS = int(os.environ.get("SKILLS_REGISTRY_TIMEOUT_SECONDS", "10"))
REGISTRY_CACHE_TTL_SECONDS = int(os.environ.get("SKILLS_REGISTRY_CACHE_TTL_SECONDS", "600"))
DEFAULT_LIMIT = 24
MAX_LIMIT = 60

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_kind_cache: dict[str, tuple[float, str]] = {}


def _fetch(params: dict[str, str]) -> dict[str, Any]:
    url = f"{REGISTRY_BASE}/api/skills/search?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "get1agent"}
    )
    with urllib.request.urlopen(request, timeout=REGISTRY_TIMEOUT_SECONDS) as response:
        return json.loads(response.read() or b"{}")


def _map(item: dict[str, Any]) -> dict[str, Any] | None:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    raw_url = str(metadata.get("rawFileUrl") or "").strip()
    if not raw_url:
        return None
    name = str(item.get("name") or "").strip()
    if not name:
        return None
    return {
        "id": str(item.get("id") or item.get("namespace") or raw_url),
        "name": name,
        "namespace": item.get("namespace"),
        "description": str(item.get("description") or ""),
        "author": item.get("author"),
        "stars": int(item.get("stars") or 0),
        "installs": int(item.get("installs") or 0),
        "sourceUrl": item.get("sourceUrl"),
        "rawUrl": raw_url,
    }


def _classify_cached(raw_url: str, now: float) -> str:
    cached = _kind_cache.get(raw_url)
    if cached and now - cached[0] < REGISTRY_CACHE_TTL_SECONDS:
        return cached[1]
    try:
        kind = str(classify_skill(fetch_text(raw_url))["kind"])
    except Exception:  # noqa: BLE001 - unclassifiable stays unknown
        kind = "unknown"
    _kind_cache[raw_url] = (now, kind)
    return kind


def _filter_by_kind(servers: list[dict[str, Any]], wanted: str) -> list[dict[str, Any]]:
    if not servers:
        return servers
    now = time.time()
    with ThreadPoolExecutor(max_workers=min(len(servers), 12)) as pool:
        kinds = list(pool.map(lambda s: _classify_cached(s["rawUrl"], now), servers))
    kept: list[dict[str, Any]] = []
    for server, kind in zip(servers, kinds):
        server["kind"] = kind
        if kind == wanted:
            kept.append(server)
    return kept


def search_registry(query: dict[str, str]) -> dict[str, Any]:
    """Search the registry; ``kind`` (prompt|tool) classifies on demand."""
    search = (query.get("search") or "").strip()
    try:
        limit = int(query.get("limit") or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(limit, MAX_LIMIT))
    try:
        offset = int(query.get("offset") or 0)
    except (TypeError, ValueError):
        offset = 0
    offset = max(0, offset)
    kind_filter = (query.get("kind") or "").strip().lower()
    if kind_filter not in ("prompt", "tool"):
        kind_filter = ""

    params: dict[str, str] = {"q": search, "limit": str(limit), "offset": str(offset)}
    cache_key = urllib.parse.urlencode(sorted({**params, "kind": kind_filter}.items()))
    cached = _cache.get(cache_key)
    now = time.time()
    if cached and now - cached[0] < REGISTRY_CACHE_TTL_SECONDS:
        return cached[1]

    try:
        data = _fetch(params)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {"skills": [], "total": 0, "limit": limit, "offset": offset, "error": str(exc)}

    skills: list[dict[str, Any]] = []
    for item in data.get("skills") or []:
        if isinstance(item, dict):
            mapped = _map(item)
            if mapped:
                skills.append(mapped)

    if kind_filter:
        skills = _filter_by_kind(skills, kind_filter)

    result = {
        "skills": skills,
        "total": int(data.get("total") or len(skills)),
        "limit": limit,
        "offset": offset,
    }
    _cache[cache_key] = (now, result)
    return result
