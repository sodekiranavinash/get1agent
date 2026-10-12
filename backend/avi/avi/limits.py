"""Avi's per-caller rate limiting.

This is the **second** layer, not the first. API Gateway throttles the route
volumetrically before any Lambda runs; this layer is per-caller fairness, using
the platform's own atomic DynamoDB counter (``core.ratelimit``) so the cap holds
across concurrently running Lambdas, and so a second ingress path cannot bypass
it.

Two windows per caller — hour and day — because they fail differently: the hour
cap stops a burst, the day cap stops a patient script. Signed-in users get
generous numbers (they are described as unlimited in the product, but a leaked
token must still be bounded); guests are capped hard per IP hash.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from core import ratelimit

from avi import settings

SURFACE_USER = "user"
SURFACE_GUEST = "guest"
SURFACE_EVAL = "eval"


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


def _limits(caller: Caller) -> tuple[int, int]:
    """``(per_hour, per_day)`` for this caller. Zero means no limit."""
    config = settings.live()
    if caller.surface == SURFACE_GUEST:
        return int(config.get("guestPerHour") or 0), int(config.get("guestPerDay") or 0)
    return int(config.get("userPerHour") or 0), int(config.get("userPerDay") or 0)


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

    per_hour, per_day = _limits(caller)
    # Zero means "no cap configured" (an admin turning the limit off).
    if per_hour <= 0 and per_day <= 0:
        return True, 0

    if per_hour > 0:
        # The daily limit only applies once the hourly one is consumed, so a
        # caller under both is not charged twice for the same request.
        if not ratelimit.allow(caller.key, kind="avi-hour", limit=per_hour, window_seconds=3600):
            return False, _seconds_until("avi-hour", 3600)
    if per_day > 0:
        if not ratelimit.allow(
            caller.key, kind="avi-day", limit=per_day, window_seconds=86_400
        ):
            return False, _seconds_until("avi-day", 86_400)
    return True, 0


def usage(caller: Caller) -> dict[str, int | str]:
    """Current consumption, for the admin page and diagnostics."""
    per_hour, per_day = _limits(caller)
    return {
        "scope": caller.scope,
        "hourUsed": ratelimit.current(caller.key, kind="avi-hour", window_seconds=3600),
        "hourLimit": per_hour,
        "dayUsed": ratelimit.current(caller.key, kind="avi-day", window_seconds=86_400),
        "dayLimit": per_day,
    }
