"""Semantic cache: return a cached result for the nearest previous query.

Uses **Upstash Vector** (a serverless vector DB, REST/HTTP, no VPC) as the
approximate-nearest-neighbour index and stores the cached payload in the vector's
raw ``data`` field. Vectors are isolated by **namespace = userId**, so one user's
cached answer can never satisfy another's request.

Flow: the caller embeds the query (it already does, for retrieval), asks this
module for the nearest cached entry above ``SEMANTIC_CACHE_THRESHOLD`` whose
metadata still matches (e.g. same knowledge-base set) and has not expired, and
only on a miss runs the real work and stores the result back.

Best-effort like ``core.cache``: disabled without credentials, every error
swallowed, so it can never break a request.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

_TIMEOUT_SECONDS = 2.0
_ID_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _config() -> tuple[str, str] | None:
    url = (os.environ.get("UPSTASH_VECTOR_REST_URL") or "").strip().rstrip("/")
    token = (os.environ.get("UPSTASH_VECTOR_REST_TOKEN") or "").strip()
    if not (url and token):
        return None
    return url, token


def enabled() -> bool:
    if (os.environ.get("SEMANTIC_CACHE_ENABLED") or "true").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    return _config() is not None


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return max(int(os.environ.get(name, str(default))), 0)
    except (TypeError, ValueError):
        return default


def threshold() -> float:
    return min(max(_env_float("SEMANTIC_CACHE_THRESHOLD", 0.95), 0.0), 1.0)


def ttl_seconds() -> int:
    return _env_int("SEMANTIC_CACHE_TTL_SECONDS", 600)


def _max_bytes() -> int:
    return _env_int("SEMANTIC_CACHE_MAX_BYTES", 200_000)


def _namespace(user_id: str) -> str:
    return _ID_SAFE.sub("_", str(user_id or ""))[:120] or "default"


def _request(path: str, payload: dict[str, Any]) -> Any:
    config = _config()
    if config is None:
        return None
    url, token = config
    request = urllib.request.Request(
        f"{url}{path}",
        data=json.dumps(payload).encode(),
        headers={
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return json.loads(response.read() or b"{}")
    except Exception as exc:  # noqa: BLE001 - cache must never break a request
        print(f"semantic cache unavailable: {exc!r}", file=sys.stderr)
        return None


def lookup(
    *,
    user_id: str,
    vector: list[float],
    require: dict[str, Any] | None = None,
) -> Any | None:
    """Return the cached payload for the nearest query above threshold, else None."""
    if not enabled() or not vector:
        return None
    response = _request(
        f"/query/{_namespace(user_id)}",
        {"vector": vector, "topK": 3, "includeMetadata": True, "includeData": True},
    )
    hits = (response or {}).get("result") or []
    if not isinstance(hits, list):
        return None
    cutoff = threshold()
    now = time.time()
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        try:
            score = float(hit.get("score") or 0)
        except (TypeError, ValueError):
            continue
        if score < cutoff:
            continue
        metadata = hit.get("metadata") or {}
        try:
            if float(metadata.get("expiresAt") or 0) <= now:
                continue
        except (TypeError, ValueError):
            continue
        if require and any(
            str(metadata.get(key)) != str(value) for key, value in require.items()
        ):
            continue
        data = hit.get("data")
        if not isinstance(data, str) or not data:
            continue
        try:
            return json.loads(data)
        except ValueError:
            continue
    return None


def store(
    *,
    user_id: str,
    vector: list[float],
    value: Any,
    vector_id: str,
    require: dict[str, Any] | None = None,
) -> None:
    """Upsert a cached payload keyed by the query embedding."""
    if not enabled() or not vector:
        return
    try:
        data = json.dumps(value)
    except (TypeError, ValueError):
        return
    if len(data) > _max_bytes():
        return
    metadata: dict[str, Any] = {
        "expiresAt": int(time.time()) + ttl_seconds(),
        "createdAt": int(time.time()),
    }
    for key, item in (require or {}).items():
        metadata[key] = str(item)
    safe_id = _ID_SAFE.sub("_", str(vector_id or ""))[:64] or hashlib.sha256(
        data.encode()
    ).hexdigest()[:32]
    _request(
        f"/upsert/{_namespace(user_id)}",
        {"id": safe_id, "vector": vector, "metadata": metadata, "data": data},
    )
