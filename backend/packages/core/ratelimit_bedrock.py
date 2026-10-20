"""Global Amazon Bedrock request-rate limiter.

Bedrock on-demand quotas are low and enforced **per account** (for example
Titan Text Embeddings V2 is 60 requests/minute), while Lambdas scale
horizontally — so an in-process limiter cannot honor them. This module keeps one
atomic counter per model per one-second window in a **shared store**. Every
worker calls :func:`throttle` immediately before a Bedrock call and waits when
the window is full, so the aggregate request rate across all concurrent Lambdas
stays within the account quota.

The store is chosen by ``BEDROCK_RATELIMIT_BACKEND`` (default: whatever
``RATELIMIT_BACKEND`` says, itself defaulting to ``auto``):

* ``auto`` / ``redis`` — the shared **Redis GCRA** limiter (the same primitive as
  ``core.ratelimit``), which reports the exact sub-second wait for the next slot.
* ``auto`` / ``dynamodb`` — the original one-second **DynamoDB** counter, polled
  until a slot frees. Used when Redis is unavailable (``auto``).

Best-effort by design: if no store is reachable (or ``BEDROCK_RATELIMIT_ENABLED``
is false) the call proceeds, and Bedrock's own throttling plus the client's
adaptive retries remain the backstop.

Configuration (all optional):
``BEDROCK_RATELIMIT_ENABLED`` (default true), ``BEDROCK_RATELIMIT_BACKEND``,
``BEDROCK_RATELIMIT_RPM`` (default 60), ``BEDROCK_RATELIMIT_MODEL`` (default
``TEXT_EMBED_MODEL``), and per-model overrides via ``BEDROCK_RATELIMIT_RPM_<MODEL>``
(model id uppercased, non-alnum -> ``_``) or a ``BEDROCK_RATELIMIT_RPM_MAP`` JSON
object.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from typing import Any

DEFAULT_RPM = 60
DEFAULT_MODEL = "amazon.titan-embed-text-v2:0"
_WINDOW_SECONDS = 1
_MAX_WAIT_SECONDS = 30.0
_SAFE = re.compile(r"[^A-Za-z0-9]+")
#: Redis policy namespace for these keys (kept distinct from the per-identity
#: policies so a model's window can never collide with a user's).
_POLICY = "bedrock"


def backend() -> str:
    """``auto`` | ``redis`` | ``dynamodb`` — Redis first unless told otherwise."""
    return (
        (os.environ.get("BEDROCK_RATELIMIT_BACKEND") or "").strip().lower()
        or (os.environ.get("RATELIMIT_BACKEND") or "auto").strip().lower()
        or "auto"
    )


def _redis_usable() -> bool:
    if backend() not in ("auto", "redis"):
        return False
    try:
        from . import redis_client  # noqa: PLC0415 - optional dependency
    except Exception:  # noqa: BLE001
        return False
    return redis_client.available()


def _dynamo_enabled() -> bool:
    return backend() in ("auto", "dynamodb") and bool(_table_name())


def enabled() -> bool:
    if (os.environ.get("BEDROCK_RATELIMIT_ENABLED") or "true").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    return _redis_usable() or _dynamo_enabled()


def _table_name() -> str:
    try:
        from data import client

        return client.table_name()
    except Exception:  # noqa: BLE001 - optional shared dependency
        return (os.environ.get("DYNAMODB_TABLE") or "").strip()


def model_id() -> str:
    return (
        (os.environ.get("BEDROCK_RATELIMIT_MODEL") or "").strip()
        or (os.environ.get("TEXT_EMBED_MODEL") or "").strip()
        or DEFAULT_MODEL
    )


def _int(name: str, default: int) -> int:
    try:
        return max(int(os.environ.get(name, str(default))), 1)
    except (TypeError, ValueError):
        return default


def rpm(model: str | None = None) -> int:
    """Requests/minute allowed for ``model`` (default model when omitted)."""
    target = (model or model_id()).strip()
    override = os.environ.get(
        "BEDROCK_RATELIMIT_RPM_" + _SAFE.sub("_", target).upper().strip("_")
    )
    if override:
        return _int_from(override, DEFAULT_RPM)
    raw_map = os.environ.get("BEDROCK_RATELIMIT_RPM_MAP")
    if raw_map:
        try:
            mapping = json.loads(raw_map)
            if isinstance(mapping, dict) and target in mapping:
                return _int_from(str(mapping[target]), DEFAULT_RPM)
        except (TypeError, ValueError):
            pass
    return _int("BEDROCK_RATELIMIT_RPM", DEFAULT_RPM)


def _int_from(value: str, default: int) -> int:
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return default


def _per_window(model: str) -> int:
    # Requests allowed per one-second window (ceil of rpm / 60).
    return max(1, -(-rpm(model) // 60))


def _window(target: str, per_window: int) -> Any:
    """A one-second GCRA window admitting ``per_window`` requests."""
    from .ratelimit import Window  # noqa: PLC0415 - optional dependency

    return Window(name="second", limit=max(int(per_window), 1), seconds=_WINDOW_SECONDS)


def _redis_wait(target: str, window: Any) -> float | None:
    """Seconds until the next slot (``0.0`` when admitted); ``None`` if no Redis."""
    if not _redis_usable():
        return None
    try:
        from .ratelimit import gcra  # noqa: PLC0415 - optional dependency
    except Exception:  # noqa: BLE001
        return None
    return gcra.wait_seconds(f"model:{target}", _POLICY, [window])


def throttle(model: str | None = None) -> None:
    """Block (bounded) until a request slot for ``model`` is available."""
    if not enabled():
        return
    target = (model or model_id()).strip() or DEFAULT_MODEL
    per_window = _per_window(target)
    window = _window(target, per_window)
    deadline = time.time() + _MAX_WAIT_SECONDS
    while True:
        waited = _redis_wait(target, window)
        if waited is not None:
            if waited <= 0.0:
                return
            # Redis named the exact wait; never sleep past our own budget.
            if time.time() + waited >= deadline:
                return
            time.sleep(min(waited, 0.25) + random.uniform(0.0, 0.02))
            continue
        if not _dynamo_enabled():
            return
        second = int(time.time())
        if _consume(target, second, per_window):
            return
        if time.time() >= deadline:
            return
        sleep_for = (second + _WINDOW_SECONDS) - time.time()
        time.sleep(max(0.0, sleep_for) + random.uniform(0.0, 0.02))


def _consume(model: str, window: int, per_window: int) -> bool:
    """Atomically take one slot in ``window``; False when the window is full."""
    try:
        from data import client

        table = client.table()
    except Exception:  # noqa: BLE001 - cannot enforce -> let the call through
        return True
    try:
        response = table.update_item(
            Key={"pk": f"RATE#bedrock#{model}", "sk": f"W#{window}"},
            UpdateExpression="ADD #n :one SET expiresAt = if_not_exists(expiresAt, :ttl)",
            ExpressionAttributeNames={"#n": "n"},
            ExpressionAttributeValues={":one": 1, ":ttl": window + 120},
            ReturnValues="UPDATED_NEW",
        )
        count = int((response.get("Attributes") or {}).get("n", 1))
    except Exception:  # noqa: BLE001 - limiter must never break a request
        return True
    return count <= per_window
