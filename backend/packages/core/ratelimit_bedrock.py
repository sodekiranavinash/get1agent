"""Global Amazon Bedrock request-rate limiter.

Bedrock on-demand quotas are low and enforced **per account** (for example
Titan Text Embeddings V2 is 60 requests/minute), while Lambdas scale
horizontally — so an in-process limiter cannot honor them. This module keeps one
atomic counter per model per one-second window in the shared DynamoDB table.
Every worker calls :func:`throttle` immediately before a Bedrock call and waits
when the window is full, so the aggregate request rate across all concurrent
Lambdas stays within the account quota.

Best-effort by design: if DynamoDB is unavailable (or ``BEDROCK_RATELIMIT_ENABLED``
is false) the call proceeds, and Bedrock's own throttling plus the client's
adaptive retries remain the backstop.

Configuration (all optional):
``BEDROCK_RATELIMIT_ENABLED`` (default true), ``BEDROCK_RATELIMIT_RPM`` (default
60), ``BEDROCK_RATELIMIT_MODEL`` (default ``TEXT_EMBED_MODEL``), and per-model
overrides via ``BEDROCK_RATELIMIT_RPM_<MODEL>`` (model id uppercased, non-alnum
-> ``_``) or a ``BEDROCK_RATELIMIT_RPM_MAP`` JSON object.
"""

from __future__ import annotations

import json
import os
import random
import re
import time

DEFAULT_RPM = 60
DEFAULT_MODEL = "amazon.titan-embed-text-v2:0"
_WINDOW_SECONDS = 1
_MAX_WAIT_SECONDS = 30.0
_SAFE = re.compile(r"[^A-Za-z0-9]+")


def enabled() -> bool:
    if (os.environ.get("BEDROCK_RATELIMIT_ENABLED") or "true").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    return bool(_table_name())


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


def throttle(model: str | None = None) -> None:
    """Block (bounded) until a request slot for ``model`` is available."""
    if not enabled():
        return
    target = (model or model_id()).strip() or DEFAULT_MODEL
    per_window = _per_window(target)
    deadline = time.time() + _MAX_WAIT_SECONDS
    while True:
        window = int(time.time())
        if _consume(target, window, per_window):
            return
        if time.time() >= deadline:
            return
        sleep_for = (window + _WINDOW_SECONDS) - time.time()
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
