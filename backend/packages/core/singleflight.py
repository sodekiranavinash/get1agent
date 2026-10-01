"""Best-effort single-flight locks (Upstash Redis REST).

Deduplicate expensive work: when several concurrent identical requests arrive,
one runs the work and the rest wait for its cached result instead of recomputing.
This is **cost deduplication, not rate limiting** — rate limiting lives at the
API Gateway (stage + per-route throttling).

Reuses :mod:`core.cache` for the Upstash REST client. Disabled without
credentials (or ``SINGLE_FLIGHT_ENABLED=false``); every call is best-effort.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable

from . import cache


def enabled() -> bool:
    if (os.environ.get("SINGLE_FLIGHT_ENABLED") or "true").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    return cache.enabled()


def _env_int(name: str, default: int) -> int:
    try:
        return max(int(os.environ.get(name, str(default))), 0)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(float(os.environ.get(name, str(default))), 0.0)
    except (TypeError, ValueError):
        return default


def lock_ttl() -> int:
    return _env_int("SINGLE_FLIGHT_LOCK_SECONDS", 20)


def wait_seconds() -> float:
    return _env_float("SINGLE_FLIGHT_WAIT_SECONDS", 6.0)


def acquire(lock_key: str, ttl_seconds: int) -> bool:
    """Try to take a ``SET NX EX`` lock. True when this caller owns it."""
    if not enabled():
        return True
    result = cache._command(  # noqa: SLF001 - shared REST client
        "SET", lock_key, "1", "NX", "EX", max(int(ttl_seconds), 1)
    )
    return str(result).upper() == "OK"


def release(lock_key: str) -> None:
    if not enabled():
        return
    cache._command("DEL", lock_key)  # noqa: SLF001


def single_flight(
    *,
    lock_key: str,
    result_key: str,
    ttl_seconds: int,
    wait: float,
    compute: Callable[[], Any],
) -> Any:
    """Run ``compute`` once; concurrent callers wait for ``result_key``.

    ``compute`` is expected to populate ``result_key`` (e.g. via the exact cache)
    as a side effect. Falls back to computing locally if the winner is slow.
    """
    if not enabled() or not result_key:
        return compute()
    if acquire(lock_key, ttl_seconds):
        try:
            return compute()
        finally:
            release(lock_key)

    deadline = time.time() + max(float(wait), 0.0)
    delay = 0.1
    while time.time() < deadline:
        time.sleep(delay)
        delay = min(delay * 2, 0.5)
        cached = cache.get(result_key)
        if cached is not None:
            return cached
    return compute()
