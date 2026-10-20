"""Per-identity request limiter — Redis GCRA first, DynamoDB as the fallback.

The platform's rate limiting has three consumers: the HTTP API (per-user,
per-endpoint), the AI Assistant (per-guest and per-user windows), and the
custom-tool sandbox (network-enabled runs per hour). All three want the same
thing — "may this identity do one more of these, and if not, when may it?" — so
they share one implementation here.

``RATELIMIT_BACKEND`` chooses the store:

* ``auto`` (**default**) — Redis GCRA when it answers, the DynamoDB fixed-window
  counter from :mod:`.fixed` otherwise. The fallback is why Redis can be adopted
  without weakening enforcement: a dead cache cannot become an open door.
* ``redis`` — Redis only; fail **open** when it is unreachable (single-backend
  deployments should never block traffic on an optional dependency).
* ``dynamodb`` — the original behaviour.
* ``none`` — disable enforcement entirely.

Every call is best-effort and returns a decision object rather than raising, so a
limiter can never take a request down with it.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Sequence

from .. import redis_client

from . import fixed, gcra
from .fixed import DEFAULT_WINDOW_SECONDS
from .policy import Policy, Window, all_policies, get as get_policy, policy_id_for_route, window_name

__all__ = [
    "DEFAULT_WINDOW_SECONDS",
    "Decision",
    "Policy",
    "Window",
    "allow",
    "backend",
    "check",
    "check_windows",
    "current",
    "describe",
    "enabled",
    "limit",
    "policy_id_for_route",
    "redis_health",
    "window_name",
]


@dataclass(frozen=True)
class Decision:
    """The limiter's answer for one request."""

    allowed: bool
    backend: str
    policy: str = ""
    scope: str = "user"
    limit: int = 0
    remaining: int = 0
    retry_after: int = 0
    reset_after: int = 0
    window: str = ""

    @property
    def used(self) -> int:
        return max(0, self.limit - self.remaining)


def backend() -> str:
    """The configured preference: ``auto`` | ``redis`` | ``dynamodb`` | ``none``."""
    return (os.environ.get("RATELIMIT_BACKEND") or "auto").strip().lower() or "auto"


def redis_health() -> dict[str, Any]:
    return redis_client.health()


def _redis_usable() -> bool:
    return backend() in ("auto", "redis") and redis_client.available()


def _dynamo_allowed_backend() -> bool:
    return backend() in ("auto", "dynamodb")


def enabled() -> bool:
    """True when at least one store can enforce a limit."""
    if backend() == "none":
        return False
    return _redis_usable() or fixed.enabled()


def limit(kind: str, default: int) -> int:
    """Configured per-window limit for ``kind`` (``RATELIMIT_<KIND>_PER_WINDOW``)."""
    key = "RATELIMIT_" + kind.upper().replace("-", "_").replace(".", "_") + "_PER_WINDOW"
    try:
        return max(int(os.environ.get(key, str(default))), 1)
    except (TypeError, ValueError):
        return default


# --- checks -------------------------------------------------------------------


def check_windows(
    identity: str,
    windows: Sequence[Window],
    *,
    policy: str = "adhoc",
    scope: str = "user",
) -> Decision:
    """Consume one slot across ``windows`` (Redis one-shot, else DynamoDB)."""
    active = tuple(window for window in windows if window.limit > 0 and window.seconds > 0)
    if not identity or not active or backend() == "none":
        return Decision(
            allowed=True,
            backend="none",
            policy=policy,
            scope=scope,
            limit=active[0].limit if active else 0,
            remaining=active[0].limit if active else 0,
        )

    if _redis_usable():
        result = gcra.consume(identity, policy, active)
        if result is not None:
            return Decision(
                allowed=result.allowed,
                backend="redis",
                policy=policy,
                scope=scope,
                limit=result.limit,
                remaining=result.remaining,
                retry_after=result.retry_after,
                reset_after=result.reset_after,
                window=result.window,
            )

    if _dynamo_allowed_backend() and fixed.enabled():
        allowed, retry_after, deny_limit, remaining, denied = fixed.check(
            [(window.name, window.limit, window.seconds) for window in active],
            identity=identity,
            policy=policy,
        )
        tightest = active[0] if active else None
        return Decision(
            allowed=allowed,
            backend="dynamodb",
            policy=policy,
            scope=scope,
            limit=deny_limit or (tightest.limit if tightest else 0),
            remaining=remaining,
            retry_after=retry_after,
            reset_after=retry_after,
            window=denied,
        )

    # Nothing could enforce (Redis-only deployment, or no table configured):
    # fail open, which is the module's documented contract.
    return Decision(
        allowed=True,
        backend="none",
        policy=policy,
        scope=scope,
        limit=active[0].limit,
        remaining=active[0].limit,
    )


def check(identity: str, *, policy: str, scope: str = "user") -> Decision:
    """Consume one slot for a **named** policy (see :mod:`.policy`)."""
    resolved = get_policy(policy)
    if resolved is None or not resolved.windows:
        return Decision(allowed=True, backend="none", policy=policy, scope=scope)
    return check_windows(identity, resolved.windows, policy=policy, scope=scope)


def allow(
    identity: str,
    *,
    kind: str,
    limit: int,  # noqa: A002 - kept for the original call signature
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
    scope: str = "user",
) -> bool:
    """Boolean shorthand used by the sandbox paths (``custom-tools``).

    Kept as a **single-window** call so the DynamoDB fallback keeps the original
    key layout (``RATE#<kind>#<identity>``) that :func:`current` still reads.
    """
    if not identity or backend() == "none":
        return True
    window = Window(
        name=window_name(window_seconds), limit=int(limit), seconds=int(window_seconds)
    )
    if _redis_usable():
        result = gcra.consume(identity, kind, [window])
        if result is not None:
            return result.allowed
    if _dynamo_allowed_backend() and fixed.enabled():
        return fixed.allow(
            identity, kind=kind, limit=limit, window_seconds=window_seconds
        )
    return True


def current(
    identity: str,
    *,
    kind: str,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
    limit: int = 0,  # noqa: A002 - only needed for the Redis (GCRA) path
    policy: str = "",
) -> int:
    """Slots already consumed in the current window.

    ``kind`` is the legacy **single-window** namespace (what ``allow`` writes).
    When the window was written by :func:`check_windows` instead, pass its
    ``policy`` **and** the window's ``name`` as ``kind`` so the read mirrors the
    write on both backends (``RATE#<policy>:<name>#`` / ``rl:{id}:<policy>:<name>``).

    GCRA stores a timestamp, not a counter, so the Redis path derives the count
    from the remaining headroom and therefore needs ``limit``. Callers that
    report usage should pass it; without it the DynamoDB counter is read, which
    is 0 on a Redis-enforced deployment.
    """
    if not identity:
        return 0
    if limit > 0 and _redis_usable():
        # With a policy, ``kind`` is already the window name as written by
        # ``gcra.consume``; otherwise the window name is derived from the size.
        name = kind if policy else window_name(window_seconds)
        window = Window(name=name, limit=int(limit), seconds=int(window_seconds))
        peeked = gcra.peek(identity, policy or kind, [window])
        if peeked:
            remaining, _retry = peeked[0]
            return max(0, int(limit) - remaining)
    return fixed.current(identity, kind=kind, window_seconds=window_seconds, policy=policy)


# --- reporting ----------------------------------------------------------------


def describe(
    identity: str,
    *,
    scope: str = "user",
    policies: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Read-only snapshot of the caller's limits, for the usage page.

    Never consumes a slot: the Redis path uses the peek script.
    """
    ids = list(policies) if policies is not None else [policy.id for policy in all_policies()]
    out: list[dict[str, Any]] = []
    for policy_id in ids:
        resolved = get_policy(policy_id)
        if resolved is None or not resolved.windows:
            continue
        configured = [window for window in resolved.windows if window.limit > 0]
        if not configured:
            continue
        rows: list[dict[str, Any]] = []
        peeked: list[tuple[int, int]] | None = None
        if identity and _redis_usable():
            peeked = gcra.peek(identity, policy_id, configured)
        for index, window in enumerate(configured):
            if peeked is not None and index < len(peeked):
                remaining, reset_after = peeked[index]
            else:
                used = fixed.current(identity, kind=f"{policy_id}:{window.name}", window_seconds=window.seconds)
                remaining, reset_after = max(0, window.limit - used), 0
            rows.append(
                {
                    "name": window.name,
                    "limit": window.limit,
                    "windowSeconds": window.seconds,
                    "used": max(0, window.limit - remaining),
                    "remaining": remaining,
                    "resetSeconds": reset_after,
                    "exceeded": remaining <= 0,
                }
            )
        out.append(
            {
                "id": policy_id,
                "description": resolved.description,
                "windows": rows,
            }
        )
    effective = "redis" if _redis_usable() else ("dynamodb" if fixed.enabled() and backend() != "none" else "none")
    return {
        "scope": scope,
        "backend": effective,
        "backendPreference": backend(),
        "enforced": effective != "none",
        "checkedAt": int(time.time()),
        "policies": out,
    }
