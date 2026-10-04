"""Semantic cache: return a cached result for the nearest previous query.

Uses the platform **S3 Vectors** store (one index per user, the same store the
knowledge index uses) as the approximate-nearest-neighbour index: cached entries
carry ``kind="semcache"`` so they never surface in knowledge search, and the
cached payload lives in the shared cache backend (DynamoDB) referenced by the
vector's key.

Flow: the caller embeds the query (it already does, for retrieval), asks this
module for the nearest cached entry above ``SEMANTIC_CACHE_THRESHOLD`` whose
metadata still matches (e.g. same knowledge-base set) and has not expired, and
only on a miss runs the real work and stores the result back.

Best-effort like ``core.cache``: disabled when the cache backend is off, every
error swallowed, so it can never break a request.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from typing import Any

from retrieval.s3_vectors import VectorRecord, vector_store

_ID_SAFE = re.compile(r"[^A-Za-z0-9_.-]")
_KIND = "semcache"


def _cache():
    try:
        from core import cache
    except Exception:  # noqa: BLE001 - semantic cache is optional
        return None
    return cache


def enabled() -> bool:
    if (os.environ.get("SEMANTIC_CACHE_ENABLED") or "true").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    cache = _cache()
    return cache is not None and cache.enabled()


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


def _safe_id(value: str) -> str:
    return _ID_SAFE.sub("_", str(value or ""))[:64]


def _payload_key(user_id: str, vector_id: str) -> str:
    cache = _cache()
    if cache is None:
        return ""
    return cache.cache_key(_KIND, user_id, vector_id)


def lookup(
    *,
    user_id: str,
    vector: list[float],
    require: dict[str, Any] | None = None,
) -> Any | None:
    """Return the cached payload for the nearest query above threshold, else None."""
    if not enabled() or not vector:
        return None
    filters: dict[str, Any] = {"kind": _KIND}
    for key, value in (require or {}).items():
        filters[key] = str(value)
    try:
        matches = vector_store().query(user_id, vector, top_k=3, filters=filters)
    except Exception as exc:  # noqa: BLE001 - cache must never break a request
        print(f"semantic cache unavailable: {exc!r}", file=sys.stderr)
        return None

    cache = _cache()
    if cache is None:
        return None
    cutoff = threshold()
    now = time.time()
    for match in matches:
        if match.score < cutoff:
            continue
        metadata = match.metadata or {}
        try:
            if float(metadata.get("expiresAt") or 0) <= now:
                continue
        except (TypeError, ValueError):
            continue
        payload = cache.get(_payload_key(user_id, match.key))
        if payload is not None:
            return payload
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
    ttl = ttl_seconds()
    metadata: dict[str, Any] = {
        "kind": _KIND,
        "expiresAt": int(time.time()) + ttl,
    }
    for key, item in (require or {}).items():
        metadata[str(key)] = str(item)
    safe_id = _safe_id(vector_id) or hashlib.sha256(data.encode()).hexdigest()[:32]
    try:
        vector_store().upsert(
            user_id,
            [VectorRecord(key=safe_id, vector=vector, filterable=metadata)],
        )
    except Exception as exc:  # noqa: BLE001
        print(f"semantic cache store failed: {exc!r}", file=sys.stderr)
        return
    cache = _cache()
    if cache is not None:
        cache.set(_payload_key(user_id, safe_id), value, ttl)
