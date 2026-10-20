"""Semantic cache on Redis **RediSearch** vector index (``FT.CREATE``/``FT.SEARCH``).

Redis Stack and Redis 8 both expose RediSearch, so a per-user cosine index gives
the semantic cache an in-memory ANN to score the current query's embedding
against — far faster than the S3 Vectors round trip, and with no extra Python
dependency (the raw ``FT.*`` commands, not the RedisVL package: keeping numpy and
its transitive tree out of the Lambda zip matters, and the index here is one
vector field plus one tag).

Layout — one index per user per embedding dimension::

    index   g1a:semcache:{<userId>}:<dim>
    doc     g1a:semcache:doc:{<userId>}:<dim>:<element>
              vec    FLOAT32[dim]  (binary)
              kbTag  TAG           (hash of the requirement set, e.g. the KB set)

The ``kbTag`` is a hash rather than the raw knowledge-base names so the TAG
query never needs escaping (KB names contain hyphens and the set is joined with
commas — both special to RediSearch). Documents carry a Redis ``EXPIRE``, so an
entry disappearing from the index and from memory is the same event.

``FT.SEARCH … KNN`` returns cosine **distance** (0 identical), so the module
reports ``similarity = 1 - distance`` to match the S3 Vectors scale and the
shared threshold.

Best-effort like the rest of the cache: every call swallows errors and returns
"no match", so an unavailable or RediSearch-less Redis degrades to a miss.
"""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from typing import Any

#: Indexes this process created (``FT.CREATE`` is idempotent, but re-checking
#: costs a round trip; we only pay it once per index per container).
_CREATED: set[str] = set()
#: Does this Redis answer ``FT.SEARCH``? Probed once per process.
_SUPPORTED: bool | None = None


def reset() -> None:
    """Forget the probe and known indexes (tests, or a Redis URL change)."""
    global _SUPPORTED
    _SUPPORTED = None
    _CREATED.clear()


def _redis() -> Any:
    try:
        from . import redis_client
    except Exception:  # noqa: BLE001
        return None
    if not redis_client.available():
        return None
    return redis_client.client()


def _note_failure() -> None:
    try:
        from . import redis_client

        redis_client.record_failure()
    except Exception:  # noqa: BLE001
        pass


def _note_success() -> None:
    try:
        from . import redis_client

        redis_client.record_success()
    except Exception:  # noqa: BLE001
        pass


def _prefix() -> str:
    try:
        from . import redis_client

        return redis_client.prefix()
    except Exception:  # noqa: BLE001
        return "g1a:"


def index_name(user_id: str, dim: int) -> str:
    safe = str(user_id or "").strip() or "anonymous"
    return f"{_prefix()}semcache:{{{safe}}}:{int(dim)}"


def _doc_prefix(user_id: str, dim: int) -> str:
    safe = str(user_id or "").strip() or "anonymous"
    return f"{_prefix()}semcache:doc:{{{safe}}}:{int(dim)}:"


def supported() -> bool:
    """True when the connected Redis exposes RediSearch (cached per process)."""
    global _SUPPORTED
    if _SUPPORTED is not None:
        return _SUPPORTED
    redis = _redis()
    if redis is None:
        return False
    try:
        info = redis.execute_command("COMMAND", "INFO", "FT.SEARCH")
    except Exception as exc:  # noqa: BLE001
        print(f"semantic cache: RediSearch probe failed: {exc!r}", file=sys.stderr)
        return False
    # redis-py 8 parses ``COMMAND INFO`` into ``{"FT.SEARCH": {...}}``; older
    # versions (and our test double) return the raw ``[[name, arity, …]]`` array.
    # Keys may arrive as bytes when the client is not decoding responses.
    if isinstance(info, dict):
        _SUPPORTED = bool(_field(info, "FT.SEARCH"))
    else:
        _SUPPORTED = bool(isinstance(info, (list, tuple)) and info and info[0])
    return _SUPPORTED


def available() -> bool:
    return supported()


def _is_missing_index(exc: Exception) -> bool:
    message = str(exc).lower()
    return "no such index" in message or "unknown index name" in message


def _blob(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *[float(value) for value in vector])


def _float(value: Any) -> float:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", "ignore")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _field(mapping: Any, name: str) -> Any:
    """A dict field by name, tolerating byte keys (a non-decoding client)."""
    if not isinstance(mapping, dict):
        return None
    if name in mapping:
        return mapping[name]
    return mapping.get(name.encode("utf-8"))


def _ensure_index(user_id: str, dim: int) -> bool:
    name = index_name(user_id, dim)
    if name in _CREATED:
        return True
    redis = _redis()
    if redis is None:
        return False
    try:
        redis.execute_command(
            "FT.CREATE",
            name,
            "ON", "HASH",
            "PREFIX", "1", _doc_prefix(user_id, dim),
            "SCHEMA",
            "vec", "VECTOR", "FLAT", "6", "TYPE", "FLOAT32", "DIM", str(int(dim)),
            "DISTANCE_METRIC", "COSINE",
            "kbTag", "TAG",
        )
        _note_success()
    except Exception as exc:  # noqa: BLE001
        if "index already exists" not in str(exc).lower():
            _note_failure()
            print(f"semantic cache: FT.CREATE failed: {exc!r}", file=sys.stderr)
            return False
        _note_success()
    _CREATED.add(name)
    return True


def _element(doc_key: Any, doc_prefix: str) -> str:
    key = doc_key.decode("utf-8", "ignore") if isinstance(doc_key, bytes) else str(doc_key)
    return key[len(doc_prefix):] if key.startswith(doc_prefix) else key


def _rows(result: Any, doc_prefix: str) -> list[tuple[str, float]]:
    """Normalise a ``FT.SEARCH`` reply to ``[(element, distance)]``.

    redis-py may return a parsed ``{"results": [{"id", "extra_attributes"}]}``
    object or the raw ``[total, key, [field, value, …], …]`` array depending on
    version, so both are handled — with str or byte keys.
    """
    out: list[tuple[str, float]] = []
    if isinstance(result, dict):
        for row in _field(result, "results") or []:
            key = _field(row, "id")
            score = _field(_field(row, "extra_attributes") or {}, "score")
            if key is not None:
                out.append((_element(key, doc_prefix), _float(score)))
        return out
    if isinstance(result, (list, tuple)) and len(result) >= 2 and isinstance(result[0], int):
        index = 1
        while index < len(result):
            key = result[index]
            fields = result[index + 1] if index + 1 < len(result) else []
            score: Any = None
            if isinstance(fields, (list, tuple)):
                for position in range(0, len(fields) - 1, 2):
                    name = fields[position]
                    if isinstance(name, (bytes, bytearray)):
                        name = name.decode("utf-8", "ignore")
                    if name == "score":
                        score = fields[position + 1]
            out.append((_element(key, doc_prefix), _float(score)))
            index += 2
    return out


def nearest(
    *,
    user_id: str,
    vector: list[float],
    kb_tag: str,
    count: int = 3,
) -> tuple[str, float] | None:
    """``(element, similarity)`` for the nearest cached query in the same scope."""
    dim = len(vector or [])
    if dim <= 0:
        return None
    redis = _redis()
    if redis is None:
        return None
    doc_prefix = _doc_prefix(user_id, dim)
    query = f"(@kbTag:{{{kb_tag}}})=>[KNN {max(int(count), 1)} @vec $blob AS score]"
    try:
        result = redis.execute_command(
            "FT.SEARCH",
            index_name(user_id, dim),
            query,
            "PARAMS", "2", "blob", _blob(vector),
            "SORTBY", "score",
            "DIALECT", "2",
            "RETURN", "1", "score",
        )
    except Exception as exc:  # noqa: BLE001 - a cache miss is never fatal
        if _is_missing_index(exc):
            _CREATED.discard(index_name(user_id, dim))
            return None
        _note_failure()
        print(f"semantic cache: FT.SEARCH failed: {exc!r}", file=sys.stderr)
        return None
    _note_success()
    rows = _rows(result, doc_prefix)
    if not rows:
        return None
    element, distance = min(rows, key=lambda row: row[1])
    # Cosine distance -> similarity, so the shared threshold applies unchanged.
    return element, 1.0 - distance


def store(
    *,
    user_id: str,
    vector: list[float],
    element: str,
    kb_tag: str,
    ttl_seconds: int,
) -> None:
    """Index ``element`` with its embedding; Redis TTL bounds the index's life."""
    dim = len(vector or [])
    if dim <= 0 or not element:
        return
    if not _ensure_index(user_id, dim):
        return
    redis = _redis()
    if redis is None:
        return
    key = _doc_prefix(user_id, dim) + element
    try:
        redis.hset(key, mapping={"vec": _blob(vector), "kbTag": str(kb_tag)})
        if int(ttl_seconds) > 0:
            redis.expire(key, int(ttl_seconds))
        _note_success()
    except Exception as exc:  # noqa: BLE001
        _note_failure()
        print(f"semantic cache: HSET failed: {exc!r}", file=sys.stderr)


def tag_for(require: dict[str, Any] | None) -> str:
    """A stable, query-safe TAG for a requirement set (e.g. the KB signature)."""
    payload = json.dumps(sorted((str(k), str(v)) for k, v in (require or {}).items()))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
