"""DynamoDB fixed-window counter — the rate limiter's fallback backend.

This is the original platform limiter: one atomic counter per identity per
window in the shared ``get1agent`` table (``RATE#<kind>#<identity>`` /
``W#<window>`` with a TTL), so the cap holds across concurrently running Lambdas.

It stays as the **fallback** used when Redis is unavailable (``RATELIMIT_BACKEND``
of ``auto``), and as the explicit backend for anyone who wants the old behaviour
(``dynamodb``). It is deliberately a *fixed* window: unlike Redis it cannot run
several windows in one atomic step, so a denial in a later window leaves the
earlier windows consumed. That approximation is acceptable precisely because
this path only runs while Redis is down.

Best-effort by design: if DynamoDB is unavailable the call is allowed through.
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


def table_name() -> str:
    try:
        from data import client

        return client.table_name()
    except Exception:  # noqa: BLE001 - optional shared dependency
        return (os.environ.get("DYNAMODB_TABLE") or "").strip()


def enabled() -> bool:
    return bool(table_name())


def allow(
    identity: str,
    *,
    kind: str,
    limit: int,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> bool:
    """Consume one slot for ``identity``; True when under ``limit`` for the window."""
    if not identity or not enabled():
        return True
    window = int(time.time() // max(int(window_seconds), 1))
    try:
        from data import client

        table = client.table()
    except Exception:  # noqa: BLE001 - cannot enforce -> let the call through
        return True
    try:
        response = table.update_item(
            Key={"pk": f"RATE#{kind}#{identity}", "sk": f"W#{window}"},
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
    identity: str,
    *,
    kind: str,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
    policy: str = "",
) -> int:
    """Read (best-effort) the slots already consumed in the current window.

    Pass ``policy`` to read a window written by :func:`check` (which namespaces
    its keys as ``<policy>:<window>``); omit it to read the legacy single-window
    key that :func:`allow` writes.
    """
    if not identity or not enabled():
        return 0
    key_kind = f"{policy}:{kind}" if policy else kind
    window = int(time.time() // max(int(window_seconds), 1))
    try:
        from data import client

        item = (
            client.table()
            .get_item(Key={"pk": f"RATE#{key_kind}#{identity}", "sk": f"W#{window}"})
            .get("Item")
            or {}
        )
        return int(item.get("n", 0))
    except Exception:  # noqa: BLE001 - reporting must never break a request
        return 0


def check(windows: list[tuple[str, int, int]], *, identity: str, policy: str) -> tuple[bool, int, int, int, str]:
    """Consume one slot across ``[(name, limit, window_seconds)]`` sequentially.

    Returns ``(allowed, retry_after_seconds, limit, remaining, denied_window)``.
    Windows are consumed in the order given (shortest first), matching the
    original behaviour: the first denial stops the walk.
    """
    for name, limit, window_seconds in windows:
        if limit <= 0:
            continue
        if not allow(identity, kind=f"{policy}:{name}", limit=limit, window_seconds=window_seconds):
            used = current(identity, kind=f"{policy}:{name}", window_seconds=window_seconds)
            boundary = (int(time.time()) // window_seconds + 1) * window_seconds
            return False, max(1, boundary - int(time.time()) + 1), limit, max(0, limit - used), name
    remaining = 0
    limit = 0
    for name, window_limit, window_seconds in windows:
        if window_limit <= 0:
            continue
        used = current(identity, kind=f"{policy}:{name}", window_seconds=window_seconds)
        left = max(0, window_limit - used)
        if not limit or left < remaining:
            limit, remaining = window_limit, left
    return True, 0, limit, remaining, ""
