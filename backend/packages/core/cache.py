"""Best-effort response cache.

Used on the **normal request path only** (query/document embeddings and
knowledge search) — never in the Labs (Playground / Evaluations), where fresh
outputs matter.

Backend is selected by ``CACHE_BACKEND``:

* ``dynamodb`` (default) — one item per entry in the shared ``get1agent`` table
  (``pk=CACHE#<prefix><kind>``, ``sk=<sha256>``, TTL ``expiresAt``), so there is
  no external cache service.
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


def backend() -> str:
    return (os.environ.get("CACHE_BACKEND") or "dynamodb").strip().lower()


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

    from boto3.dynamodb.types import TypeDeserializer

    deserializer = TypeDeserializer()
    for start in range(0, len(request_keys), _DDB_BATCH):
        chunk = request_keys[start : start + _DDB_BATCH]
        try:
            response = client.batch_get_item(RequestItems={name: {"Keys": chunk}})
        except Exception:  # noqa: BLE001
            return out
        for raw in (response.get("Responses") or {}).get(name, []):
            item = {k: deserializer.deserialize(v) for k, v in raw.items()}
            position = index.get((item.get("pk"), item.get("sk")))
            if position is None:
                continue
            if _unexpired(item) is None:
                continue
            out[position] = _decode(item.get("payload"))
    return out


def _ddb_set(key: str, value: Any, ttl_seconds: int) -> None:
    encoded = _encode(value)
    if encoded is None:
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
            if encoded is None:
                continue
            pk, sk = _pk_sk(key)
            item: dict[str, Any] = {"pk": pk, "sk": sk, "payload": encoded}
            if ttl_seconds > 0:
                item["expiresAt"] = _now() + ttl_seconds
            writer.put_item(Item=item)


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
    return _ddb_get(key)


def set(key: str, value: Any, ttl_seconds: int) -> None:  # noqa: A001 - cache API
    if not enabled():
        return
    _ddb_set(key, value, ttl_seconds)


def get_many(keys: list[str]) -> list[Any]:
    if not keys or not enabled():
        return [None] * len(keys)
    return _ddb_get_many(keys)


def set_many(pairs: list[tuple[str, Any]], ttl_seconds: int) -> None:
    if not pairs or not enabled():
        return
    _ddb_set_many(pairs, ttl_seconds)


# --- locks (single-flight) ----------------------------------------------------


def set_nx(key: str, ttl_seconds: int) -> bool:
    """Set ``key`` only if absent. True when this caller created it."""
    if not enabled():
        return True
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


def delete(key: str) -> None:
    if not enabled():
        return
    pk, sk = _pk_sk(key)
    try:
        _table().delete_item(Key={"pk": pk, "sk": sk})
    except Exception:  # noqa: BLE001
        pass
