"""Best-effort response cache.

Used on the **normal request path only** (query/document embeddings and
knowledge search) — never in the Labs (Playground / Evaluations), where fresh
outputs matter.

Backend is selected by ``CACHE_BACKEND``:

* ``auto`` (default) — **Redis** when it answers, the DynamoDB TTL item
  otherwise. A dead Redis degrades the cache, it never breaks a request.
* ``redis`` — Redis only; a miss on failure (the caller recomputes).
* ``dynamodb`` — one item per entry in the shared ``get1agent`` table
  (``pk=CACHE#<prefix><kind>``, ``sk=<sha256>``, TTL ``expiresAt``).
* ``none`` — disabled.

When it is not configured every call is a no-op, and every operation swallows
errors: the cache must never break a request.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

_DDB_BATCH = 100

# DynamoDB items cap at 400 KB; stay well clear so the item's other attributes
# and the serialized overhead never push a cached payload over the limit.
_MAX_PAYLOAD_BYTES = int(os.environ.get("CACHE_MAX_PAYLOAD_BYTES", "300000"))


def backend() -> str:
    return (os.environ.get("CACHE_BACKEND") or "auto").strip().lower() or "auto"


def _redis_usable() -> bool:
    """True when the chosen backend includes Redis and it is answering."""
    if backend() not in ("auto", "redis"):
        return False
    try:
        from . import redis_client
    except Exception:  # noqa: BLE001 - optional dependency
        return False
    return redis_client.available()


def active_backend() -> str:
    """The backend that actually serves now: ``redis`` | ``dynamodb`` | ``none``.

    ``backend()`` is the *configuration* (and may be ``auto``); this resolves it
    against the live Redis so callers can name the store that answered — e.g. a
    cache hit shown on the run timeline.
    """
    choice = backend()
    if choice == "dynamodb":
        return "dynamodb"
    if choice in ("auto", "redis"):
        if _redis_usable():
            return "redis"
        return "dynamodb" if choice == "auto" else "none"
    return "none"


def enabled() -> bool:
    """True when a usable cache backend is configured."""
    return backend() not in ("", "none")


def prefix() -> str:
    return (os.environ.get("CACHE_PREFIX") or "g1a:").strip()


def cache_key(kind: str, *parts: Any) -> str:
    """Deterministic key: ``<prefix><kind>:<sha256(parts)>`` (payloads hashed)."""
    digest = hashlib.sha256("\x1f".join(str(part) for part in parts).encode()).hexdigest()
    return f"{prefix()}{kind}:{digest}"


def ttl(kind: str, default: int) -> int:
    """Per-kind TTL from ``CACHE_<KIND>_TTL_SECONDS`` (0 = no expiry)."""
    raw = os.environ.get(f"CACHE_{kind.upper()}_TTL_SECONDS")
    try:
        return max(int(raw), 0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# --- Redis backend ------------------------------------------------------------


def _redis_get(key: str) -> Any:
    raw = _redis_command("get", key)
    return _decode(raw) if isinstance(raw, str) else None


def _redis_get_many(keys: list[str]) -> list[Any]:
    """One ``MGET`` for the batch (the deployed instance is op-limited)."""
    redis = _redis_client()
    if redis is None:
        return [None] * len(keys)
    try:
        raw = redis.mget(keys)
    except Exception:  # noqa: BLE001
        _redis_note_failure()
        return [None] * len(keys)
    _redis_note_success()
    if not isinstance(raw, list):
        return [None] * len(keys)
    return [_decode(item) if isinstance(item, str) else None for item in raw]


def _redis_set(key: str, value: Any, ttl_seconds: int) -> None:
    encoded = _encode(value)
    if encoded is None or _too_large(encoded):
        return
    if ttl_seconds > 0:
        _redis_command("set", key, encoded, ex=int(ttl_seconds))
    else:
        _redis_command("set", key, encoded)


def _redis_set_many(pairs: list[tuple[str, Any]], ttl_seconds: int) -> None:
    redis = _redis_client()
    if redis is None:
        return
    try:
        pipe = redis.pipeline(transaction=False)
        wrote = False
        for key, value in pairs:
            encoded = _encode(value)
            if encoded is None or _too_large(encoded):
                continue
            if ttl_seconds > 0:
                pipe.set(key, encoded, ex=int(ttl_seconds))
            else:
                pipe.set(key, encoded)
            wrote = True
        if wrote:
            pipe.execute()
    except Exception:  # noqa: BLE001
        _redis_note_failure()
        return
    _redis_note_success()


def _redis_set_nx(key: str, ttl_seconds: int) -> bool | None:
    """``SET key 1 NX EX ttl``; True when this caller created it, None on failure."""
    redis = _redis_client()
    if redis is None:
        return None
    try:
        result = redis.set(key, "1", nx=True, ex=max(int(ttl_seconds), 1))
    except Exception:  # noqa: BLE001
        _redis_note_failure()
        return None
    _redis_note_success()
    return bool(result)


def _redis_delete(key: str) -> None:
    _redis_command("delete", key)


def _redis_client() -> Any:
    try:
        from . import redis_client as client
    except Exception:  # noqa: BLE001
        return None
    if not client.available():
        return None
    return client.client()


def _redis_command(fn: str, *args: Any, **kwargs: Any) -> Any:
    try:
        from . import redis_client
    except Exception:  # noqa: BLE001
        return None
    # ``redis_client.command(label, method, …)`` — the label is only for the
    # breaker/diagnostics; the method is what runs.
    return redis_client.command(f"cache.{fn}", fn, *args, **kwargs)


def _redis_note_failure() -> None:
    try:
        from . import redis_client

        redis_client.record_failure()
    except Exception:  # noqa: BLE001
        pass


def _redis_note_success() -> None:
    try:
        from . import redis_client

        redis_client.record_success()
    except Exception:  # noqa: BLE001
        pass


# --- DynamoDB backend ---------------------------------------------------------


def _table() -> Any:
    from data import client

    return client.table()


def _now() -> int:
    return int(time.time())


def _pk_sk(key: str) -> tuple[str, str]:
    """Split a cache key into a sharded partition and a sort key."""
    head, sep, tail = key.rpartition(":")
    if not sep:
        return f"CACHE#{prefix()}root", key
    return f"CACHE#{head}", tail


def _unexpired(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    expires_at = item.get("expiresAt")
    try:
        if expires_at is not None and int(expires_at) <= _now():
            return None
    except (TypeError, ValueError):
        pass
    return item


def _ddb_get(key: str) -> Any:
    try:
        pk, sk = _pk_sk(key)
        response = _table().get_item(Key={"pk": pk, "sk": sk})
    except Exception:  # noqa: BLE001
        return None
    item = _unexpired(response.get("Item"))
    if not item:
        return None
    return _decode(item.get("payload"))


#: Every value in a DynamoDB-JSON item is a single-key map keyed by its type code.
_DDB_TYPE_CODES = frozenset({"S", "N", "B", "BOOL", "NULL", "M", "L", "SS", "NS", "BS"})


def _item_from(raw: dict[str, Any]) -> dict[str, Any]:
    """A ``BatchGetItem`` item as plain Python values.

    ``_table()`` is a boto3 **resource**, and that resource's client carries the
    high-level DynamoDB transform: ``batch_get_item`` through it comes back already
    decoded (``{"pk": "CACHE#…", "expiresAt": Decimal(…)}``). The low-level shape is
    ``{"pk": {"S": "CACHE#…"}}``.

    Only the second needs a deserializer, and running the first through one raised
    ``AttributeError: 'str' object has no attribute 'keys'`` — on the first cache
    *hit*, which is exactly why it survived unnoticed: a read that misses returns no
    items at all, so the loop body never ran. Re-ingesting an already-embedded
    document, or asking the same question twice, was enough to hit it.
    """
    if raw and all(
        isinstance(value, dict) and len(value) == 1 and next(iter(value)) in _DDB_TYPE_CODES
        for value in raw.values()
    ):
        from boto3.dynamodb.types import TypeDeserializer

        deserializer = TypeDeserializer()
        return {key: deserializer.deserialize(value) for key, value in raw.items()}
    return dict(raw)


def _ddb_get_many(keys: list[str]) -> list[Any]:
    out: list[Any] = [None] * len(keys)
    table = _table()
    client = table.meta.client
    name = table.name
    index: dict[tuple[str, str], int] = {}
    request_keys: list[dict[str, str]] = []
    for position, key in enumerate(keys):
        pk, sk = _pk_sk(key)
        if (pk, sk) in index:
            continue
        index[(pk, sk)] = position
        request_keys.append({"pk": pk, "sk": sk})

    for start in range(0, len(request_keys), _DDB_BATCH):
        chunk = request_keys[start : start + _DDB_BATCH]
        try:
            response = client.batch_get_item(RequestItems={name: {"Keys": chunk}})
            for raw in (response.get("Responses") or {}).get(name, []):
                item = _item_from(raw)
                position = index.get((item.get("pk"), item.get("sk")))
                if position is None:
                    continue
                if _unexpired(item) is None:
                    continue
                out[position] = _decode(item.get("payload"))
        except Exception:  # noqa: BLE001 - the cache may never break a request
            # Deliberately wider than the call itself: a decoding failure has to
            # degrade to a miss too, which is this module's documented contract.
            continue
    return out


def _too_large(encoded: str) -> bool:
    """True when a payload cannot fit a DynamoDB item.

    A cached search response carries the full parent text of up to 50 hits, so
    it can exceed the 400 KB item limit. Writing it would raise and (because
    every cache operation swallows errors) silently turn into a permanent miss;
    skipping the write up front keeps that explicit and cheap.
    """
    return len(encoded.encode("utf-8")) > _MAX_PAYLOAD_BYTES


def _ddb_set(key: str, value: Any, ttl_seconds: int) -> None:
    encoded = _encode(value)
    if encoded is None or _too_large(encoded):
        return
    pk, sk = _pk_sk(key)
    item: dict[str, Any] = {"pk": pk, "sk": sk, "payload": encoded}
    if ttl_seconds > 0:
        item["expiresAt"] = _now() + ttl_seconds
    try:
        _table().put_item(Item=item)
    except Exception:  # noqa: BLE001
        pass


def _ddb_set_many(pairs: list[tuple[str, Any]], ttl_seconds: int) -> None:
    table = _table()
    with table.batch_writer() as writer:
        for key, value in pairs:
            encoded = _encode(value)
            if encoded is None or _too_large(encoded):
                continue
            pk, sk = _pk_sk(key)
            item: dict[str, Any] = {"pk": pk, "sk": sk, "payload": encoded}
            if ttl_seconds > 0:
                item["expiresAt"] = _now() + ttl_seconds
            writer.put_item(Item=item)


def _ddb_set_nx(key: str, ttl_seconds: int) -> bool:
    """DynamoDB conditional put. True when this caller created the key."""
    pk, sk = _pk_sk(key)
    item: dict[str, Any] = {"pk": pk, "sk": sk, "payload": "1"}
    if ttl_seconds > 0:
        item["expiresAt"] = _now() + ttl_seconds
    try:
        _table().put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        try:
            from data.client import is_conditional_failure

            if is_conditional_failure(exc):
                return False
        except Exception:  # noqa: BLE001
            pass
        return True


def _ddb_delete(key: str) -> None:
    pk, sk = _pk_sk(key)
    try:
        _table().delete_item(Key={"pk": pk, "sk": sk})
    except Exception:  # noqa: BLE001
        pass


def _encode(value: Any) -> str | None:
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return None


def _decode(raw: Any) -> Any:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


# --- JSON convenience ---------------------------------------------------------


def get(key: str) -> Any:
    if not enabled():
        return None
    if _redis_usable():
        # A Redis miss is a miss: falling back to DynamoDB per key would double
        # the reads on every miss for no benefit (the DynamoDB entry is only
        # written when Redis was down).
        return _redis_get(key)
    if backend() == "redis":
        return None
    return _ddb_get(key)


def set(key: str, value: Any, ttl_seconds: int) -> None:  # noqa: A001 - cache API
    if not enabled():
        return
    if _redis_usable():
        _redis_set(key, value, ttl_seconds)
        return
    if backend() == "redis":
        return
    _ddb_set(key, value, ttl_seconds)


def get_many(keys: list[str]) -> list[Any]:
    if not keys or not enabled():
        return [None] * len(keys)
    if _redis_usable():
        return _redis_get_many(keys)
    if backend() == "redis":
        return [None] * len(keys)
    return _ddb_get_many(keys)


def set_many(pairs: list[tuple[str, Any]], ttl_seconds: int) -> None:
    if not pairs or not enabled():
        return
    if _redis_usable():
        _redis_set_many(pairs, ttl_seconds)
        return
    if backend() == "redis":
        return
    _ddb_set_many(pairs, ttl_seconds)


# --- locks (single-flight) ----------------------------------------------------


def set_nx(key: str, ttl_seconds: int) -> bool:
    """Set ``key`` only if absent. True when this caller created it."""
    if not enabled():
        return True
    if _redis_usable():
        result = _redis_set_nx(key, ttl_seconds)
        if result is not None:
            return result
        # Redis answered nothing: fail open (the caller computes) rather than
        # serialising behind a lock we could not prove we took.
        if backend() == "redis":
            return True
    elif backend() == "redis":
        return True
    return _ddb_set_nx(key, ttl_seconds)


def delete(key: str) -> None:
    if not enabled():
        return
    if _redis_usable():
        _redis_delete(key)
        return
    if backend() == "redis":
        return
    _ddb_delete(key)
