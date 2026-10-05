"""Per-user, fixed-window request limiter (shared DynamoDB counter).

Some platform operations must be capped per user — most importantly the
network-enabled custom-tool sandbox, where a user can make outbound calls on
the platform's behalf. One atomic counter per user per window lives in the
shared DynamoDB table (``RATE#<kind>#<userId>`` / ``W#<window>`` with a TTL), so
the cap holds across concurrently running Lambdas and is cheap (one update).

Best-effort by design: if DynamoDB is unavailable the call is allowed through
(the sandbox timeout and connection cap remain the backstop).
"""

from __future__ import annotations

import os
import time

DEFAULT_WINDOW_SECONDS = 3600


def _env_int(name: str, default: int) -> int:
    try:
        return max(int(os.environ.get(name, str(default))), 1)
    except (TypeError, ValueError):
        return default


def _table_name() -> str:
    try:
        from data import client

        return client.table_name()
    except Exception:  # noqa: BLE001 - optional shared dependency
        return (os.environ.get("DYNAMODB_TABLE") or "").strip()


def enabled() -> bool:
    return bool(_table_name())


def limit(kind: str, default: int) -> int:
    """Configured per-window limit for ``kind`` (``RATELIMIT_<KIND>_PER_WINDOW``)."""
    key = "RATELIMIT_" + kind.upper().replace("-", "_").replace(".", "_") + "_PER_WINDOW"
    return _env_int(key, default)


def allow(
    user_id: str,
    *,
    kind: str,
    limit: int,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> bool:
    """Consume one slot for ``user_id``; True when under ``limit`` for the window."""
    if not user_id or not enabled():
        return True
    window = int(time.time() // max(int(window_seconds), 1))
    try:
        from data import client

        table = client.table()
    except Exception:  # noqa: BLE001 - cannot enforce -> let the call through
        return True
    try:
        response = table.update_item(
            Key={"pk": f"RATE#{kind}#{user_id}", "sk": f"W#{window}"},
            UpdateExpression=(
                "ADD #n :one SET expiresAt = if_not_exists(expiresAt, :ttl)"
            ),
            ExpressionAttributeNames={"#n": "n"},
            ExpressionAttributeValues={
                ":one": 1,
                ":ttl": (window + 2) * max(int(window_seconds), 1),
            },
            ReturnValues="UPDATED_NEW",
        )
        count = int((response.get("Attributes") or {}).get("n", 1))
    except Exception:  # noqa: BLE001 - limiter must never break a request
        return True
    return count <= max(int(limit), 1)


def current(
    user_id: str,
    *,
    kind: str,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> int:
    """Read (best-effort) the slots already consumed in the current window."""
    if not user_id or not enabled():
        return 0
    window = int(time.time() // max(int(window_seconds), 1))
    try:
        from data import client

        item = (
            client.table()
            .get_item(Key={"pk": f"RATE#{kind}#{user_id}", "sk": f"W#{window}"})
            .get("Item")
            or {}
        )
        return int(item.get("n", 0))
    except Exception:  # noqa: BLE001 - reporting must never break a request
        return 0

