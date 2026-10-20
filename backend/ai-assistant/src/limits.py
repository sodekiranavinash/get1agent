"""AI Assistant's per-caller rate limiting.

This is the **second** layer, not the first. API Gateway throttles the route
volumetrically before any Lambda runs; this layer is per-caller fairness, backed
by the platform's shared limiter (``core.ratelimit``: Redis GCRA when configured,
the DynamoDB counter otherwise) so the cap holds across concurrently running
Lambdas, and so a second ingress path cannot bypass it.

Three windows per caller, checked shortest first, because they fail differently:

* **burst** (3 minutes) — a human asking a run of questions. This is the window a
  real visitor meets, and it is deliberately short so a refusal reads "try again
  in a couple of minutes", not "come back in an hour". Ten a guest, matching the
  number the product states.
* **hour** — a script with a loop.
* **day** — a patient script.

Signed-in users get generous numbers (they are described as unlimited in the
product, but a leaked token must still be bounded) and no burst cap by default;
guests are capped per IP hash.

All three windows are consumed in **one** atomic step, so the refusal is exact:
a caller stopped by the day cap is not also charged against the hour cap.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from core import ratelimit
from core.ratelimit import Window

from src import settings

SURFACE_USER = "user"
SURFACE_GUEST = "guest"
SURFACE_EVAL = "eval"

#: The policy id the shared limiter records these windows under.
POLICY = "ai-assistant"

#: The short window. Kept in one place so the settings default and the retry
#: arithmetic cannot drift apart.
BURST_WINDOW_SECONDS = 180
HOUR_WINDOW_SECONDS = 3600
DAY_WINDOW_SECONDS = 86_400


@dataclass(frozen=True)
class Caller:
    """Who is asking — the identity rate limiting is enforced against."""

    key: str
    surface: str = SURFACE_USER
    user_id: str = ""
    is_admin: bool = False

    @property
    def scope(self) -> str:
        return "admin" if self.is_admin else self.surface


def _windows(caller: Caller) -> list[tuple[str, str, int, int]]:
    """``[(name, kind, limit, window_seconds)]``, shortest window first.

    ``limit`` of zero means "no cap in this window" (an admin turning it off).
    """
    config = settings.live()
    prefix = "guest" if caller.surface == SURFACE_GUEST else "user"
    return [
        ("burst", "ai-assistant-burst", int(config.get(f"{prefix}PerBurst") or 0), BURST_WINDOW_SECONDS),
        ("hour", "ai-assistant-hour", int(config.get(f"{prefix}PerHour") or 0), HOUR_WINDOW_SECONDS),
        ("day", "ai-assistant-day", int(config.get(f"{prefix}PerDay") or 0), DAY_WINDOW_SECONDS),
    ]


def _seconds_until(kind: str, window_seconds: int) -> int:
    """Seconds until the current fixed window rolls over."""
    if not kind or window_seconds <= 0:
        return 60
    now = time.time()
    boundary = (int(now) // window_seconds + 1) * window_seconds
    return max(1, int(boundary - now) + 1)


def check_and_count(caller: Caller) -> tuple[bool, int]:
    """Consume one slot for this caller.

    Returns ``(allowed, retry_after_seconds)``. An evaluation run is exempt: it is
    an operator action, not user traffic, and it runs many turns in a row by
    design.
    """
    if caller.surface == SURFACE_EVAL:
        return True, 0

    windows = _windows(caller)
    # Every window off means "no cap configured" (an admin turning the limits off).
    if not any(limit > 0 for _, _, limit, _ in windows):
        return True, 0

    active = [
        Window(name=kind, limit=limit, seconds=window_seconds)
        for _name, kind, limit, window_seconds in windows
        if limit > 0
    ]
    decision = ratelimit.check_windows(
        caller.key, active, policy=POLICY, scope=caller.scope
    )
    if decision.allowed:
        return True, 0

    # GCRA reports the exact wait for the next slot; the DynamoDB fallback
    # reports its window rollover. Either way the refusal names a real time.
    seconds_by_kind = {
        kind: window_seconds for _name, kind, _limit, window_seconds in windows
    }
    retry = int(decision.retry_after or 0)
    if retry <= 0:
        retry = _seconds_until(
            decision.window, seconds_by_kind.get(decision.window, 60)
        )
    return False, retry


def usage(caller: Caller) -> dict[str, int | str]:
    """Current consumption, for the admin page and diagnostics."""
    out: dict[str, int | str] = {"scope": caller.scope}
    for name, kind, limit, window_seconds in _windows(caller):
        out[f"{name}Used"] = ratelimit.current(
            caller.key,
            kind=kind,
            window_seconds=window_seconds,
            # Reads the window ``check_and_count`` wrote, which is namespaced by
            # policy (:func:`core.ratelimit.check_windows`).
            policy=POLICY,
            # Redis derives the count from the remaining headroom, so it needs
            # the limit; the DynamoDB fallback ignores it.
            limit=limit,
        )
        out[f"{name}Limit"] = limit
    return out


