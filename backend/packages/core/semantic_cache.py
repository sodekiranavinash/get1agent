"""Semantic cache: return a cached result for the nearest previous query.

The caller embeds the query (it already does, for retrieval), asks this module
for the nearest cached entry above ``SEMANTIC_CACHE_THRESHOLD`` whose metadata
still matches (e.g. the same knowledge-base set), and only on a miss runs the
real work and stores the result back. The payload itself lives in the shared
cache backend (``core.cache``), referenced by the vector's id, so both backends
share the same TTL item.

The ANN index is chosen by ``SEMANTIC_CACHE_BACKEND``:

* ``auto`` (default) — **Redis** (a per-user RediSearch vector index) when it
  answers, the platform **S3 Vectors** store otherwise. Redis is the fast path:
  scoring the query against the user's cached queries is a single in-memory
  round trip instead of an S3 Vectors call.
* ``redis`` — Redis only; an unavailable Redis is a miss.
* ``s3vectors`` — the long-standing S3 Vectors path (one index per user, the
  same store the knowledge index uses, ``kind="semcache"`` entries).
* ``none`` — disabled.

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


def _redis_available() -> bool:
    try:
        from . import semantic_cache_redis
    except Exception:  # noqa: BLE001 - semantic cache is optional
        return False
    return semantic_cache_redis.available()


def backend() -> str:
    """The backend in force: ``redis`` | ``s3vectors`` | ``none``."""
    choice = (os.environ.get("SEMANTIC_CACHE_BACKEND") or "auto").strip().lower()
    if choice in ("redis", "s3vectors", "none"):
        return choice
    # auto: Redis when it answers, S3 Vectors otherwise.
    return "redis" if _redis_available() else "s3vectors"


def enabled() -> bool:
    if (os.environ.get("SEMANTIC_CACHE_ENABLED") or "true").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    if backend() == "none":
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


def _match_info(backend_name: str, vector_id: str, similarity: float) -> dict[str, Any]:
    return {
        "backend": backend_name,
        "kind": "semantic",
        "similarity": round(float(similarity), 4),
        "vectorId": vector_id,
    }


def lookup_match(
    *,
    user_id: str,
    vector: list[float],
    require: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any]] | None:
    """``(payload, info)`` for the nearest query above threshold, else ``None``.

    The ``info`` names the backend and the cosine similarity so the caller can
    surface a cache hit on the tool result.
    """
    if not enabled() or not vector:
        return None
    if backend() == "redis":
        return _lookup_redis(user_id=user_id, vector=vector, require=require)
    return _lookup_s3vectors(user_id=user_id, vector=vector, require=require)


def lookup(
    *,
    user_id: str,
    vector: list[float],
    require: dict[str, Any] | None = None,
) -> Any | None:
    """Return the cached payload for the nearest query above threshold, else None."""
    match = lookup_match(user_id=user_id, vector=vector, require=require)
    return match[0] if match else None


def _lookup_redis(
    *,
    user_id: str,
    vector: list[float],
    require: dict[str, Any] | None,
) -> tuple[Any, dict[str, Any]] | None:
    from . import semantic_cache_redis

    found = semantic_cache_redis.nearest(
        user_id=user_id,
        vector=vector,
        kb_tag=semantic_cache_redis.tag_for(require),
    )
    if not found:
        return None
    element, similarity = found
    if similarity < threshold():
        return None
    cache = _cache()
    if cache is None:
        return None
    payload = cache.get(_payload_key(user_id, element))
    if payload is None:
        return None
    return payload, _match_info("redis", element, similarity)


def _lookup_s3vectors(
    *,
    user_id: str,
    vector: list[float],
    require: dict[str, Any] | None,
) -> tuple[Any, dict[str, Any]] | None:
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
            return payload, _match_info("s3vectors", match.key, match.score)
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
    safe_id = _safe_id(vector_id) or hashlib.sha256(data.encode()).hexdigest()[:32]
    if backend() == "redis":
        from . import semantic_cache_redis

        semantic_cache_redis.store(
            user_id=user_id,
            vector=vector,
            element=safe_id,
            kb_tag=semantic_cache_redis.tag_for(require),
            ttl_seconds=ttl,
        )
    else:
        metadata: dict[str, Any] = {
            "kind": _KIND,
            "expiresAt": int(time.time()) + ttl,
        }
        for key, item in (require or {}).items():
            metadata[str(key)] = str(item)
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
