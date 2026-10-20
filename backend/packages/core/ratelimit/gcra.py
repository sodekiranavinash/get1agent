"""GCRA rate limiting in one atomic Redis round trip.

**GCRA** (the generic cell rate algorithm, the leaky-bucket variant behind
Stripe's limiter) stores a single number per identity+window — the *theoretical
arrival time* of the next allowed request — so it costs one tiny key instead of
one list member per request (a sorted-set sliding-window log). For ``N`` per
window ``T`` the emission interval is ``ei = T/N`` and the burst tolerance is
``tau = T``, which makes "60 per minute" admit 60 back-to-back and then smooth
out — the boundary doubling of a fixed window is gone.

All windows of a policy are evaluated and committed in **one** Lua script, which
matters twice over:

* *Atomically* — a denial never consumes the other windows, and two concurrent
  Lambdas cannot both see a stale count. Nothing on the platform needs a lock.
* *Cheaply* — one round trip, one EVALSHA. The deployed Redis may cap throughput
  at ~100 ops/sec, so a request that needed three counter calls is a real
  capacity regression.

The script reads the clock from Redis (``TIME``), not from the caller, so five
Lambda containers with independent clocks cannot collectively over-admit.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Sequence

from core import redis_client

from .policy import Window

CONSUME_SCRIPT = "ratelimit.gcra.consume"
PEEK_SCRIPT = "ratelimit.gcra.peek"

#: ``KEYS[i]`` holds window ``i``'s state; ``ARGV[2i-1]``/``ARGV[2i]`` are its
#: limit and window in milliseconds. Returns
#: ``{allowed, retry_ms, denied_limit, min_remaining, retry_ms, denied_index}``.
_CONSUME = """
local n = #KEYS
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)

local tats = {}
local ttls = {}
local allowed = 1
local retry_after = 0
local deny_limit = 0
local deny_index = 0
local min_remaining = -1
local min_index = 1

for i = 1, n do
  local limit = tonumber(ARGV[(i - 1) * 2 + 1])
  local window = tonumber(ARGV[(i - 1) * 2 + 2])
  tats[i] = false
  if limit ~= nil and limit > 0 and window ~= nil and window > 0 then
    local ei = window / limit
    local tau = window
    local tat = tonumber(redis.call('GET', KEYS[i]))
    if tat == nil or tat < now then tat = now end
    local new_tat = tat + ei
    local allow_at = new_tat - tau
    if allow_at > now then
      if allowed == 1 then
        allowed = 0
        retry_after = math.ceil(allow_at - now)
        deny_limit = limit
        deny_index = i
      end
    else
      local remaining = math.floor((tau - (new_tat - now)) / ei)
      if remaining < 0 then remaining = 0 end
      if min_remaining < 0 or remaining < min_remaining then
        min_remaining = remaining
        min_index = i
      end
    end
    tats[i] = new_tat
    ttls[i] = math.floor(tau + ei) + 1000
  end
end

-- Commit only when every window admitted the request: a caller stopped by the
-- daily cap must not also be charged against the minute cap.
if allowed == 1 then
  for i = 1, n do
    if tats[i] ~= false then
      redis.call('SET', KEYS[i], tostring(tats[i]))
      redis.call('PEXPIRE', KEYS[i], ttls[i])
    end
  end
end

if min_remaining < 0 then min_remaining = 0 end
return {allowed, retry_after, deny_limit, min_remaining, retry_after, deny_index, min_index}
"""

#: Read-only twin of the above, for the usage/admin surfaces. Returns a flat
#: ``{remaining_1, retry_ms_1, remaining_2, retry_ms_2, …}``.
_PEEK = """
local n = #KEYS
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local out = {}

for i = 1, n do
  local limit = tonumber(ARGV[(i - 1) * 2 + 1])
  local window = tonumber(ARGV[(i - 1) * 2 + 2])
  local remaining = -1
  local retry = 0
  if limit ~= nil and limit > 0 and window ~= nil and window > 0 then
    local ei = window / limit
    local tau = window
    local tat = tonumber(redis.call('GET', KEYS[i]))
    if tat == nil or tat < now then tat = now end
    remaining = math.floor((tau - (tat - now)) / ei)
    if remaining < 0 then remaining = 0 end
    local allow_at = tat - tau
    if allow_at > now then retry = math.ceil(allow_at - now) end
  end
  out[#out + 1] = remaining
  out[#out + 1] = retry
end

return out
"""


@dataclass(frozen=True)
class Result:
    allowed: bool
    backend: str
    retry_after: int
    limit: int
    remaining: int
    window: str
    reset_after: int

    @property
    def used(self) -> int:
        return max(0, self.limit - self.remaining)


def key(identity: str, policy: str, window: Window) -> str:
    """``<prefix>rl:{<identity>}:<policy>:<window>``.

    The braces are a Redis **hash tag**: every key for one identity hashes to the
    same slot, so all windows can be read in a single script even if the database
    is later moved behind a cluster.
    """
    safe_identity = str(identity or "").strip() or "anonymous"
    return f"{redis_client.prefix()}rl:{{{safe_identity}}}:{policy}:{window.name}"


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def consume(identity: str, policy: str, windows: Sequence[Window]) -> Result | None:
    """Take one slot across ``windows``. ``None`` when Redis did not answer."""
    active = [window for window in windows if window.limit > 0 and window.seconds > 0]
    if not identity or not active:
        return None
    keys = [key(identity, policy, window) for window in active]
    args: list[int] = []
    for window in active:
        args.extend([window.limit, window.window_ms])
    raw = redis_client.run(CONSUME_SCRIPT, _CONSUME, keys=keys, args=args)
    if not isinstance(raw, (list, tuple)) or len(raw) < 7:
        return None
    allowed = _int(raw[0]) == 1
    retry = max(_int(raw[1]), 0)
    denied_index = _int(raw[5])
    tightest_index = _int(raw[6], 1)

    def _window_at(position: int) -> Window | None:
        return active[position - 1] if 1 <= position <= len(active) else None

    denied = _window_at(denied_index)
    if not allowed:
        # The denying window is exhausted by definition; its remaining is 0.
        return Result(
            allowed=False,
            backend="redis",
            # Seconds, rounded up: a client told to wait 0 would retry immediately.
            retry_after=(retry + 999) // 1000 if retry else gcra_reset_hint(),
            limit=denied.limit if denied is not None else 0,
            remaining=0,
            window=denied.name if denied is not None else "",
            reset_after=(retry + 999) // 1000 if retry else gcra_reset_hint(),
        )
    tightest = _window_at(tightest_index) or (active[0] if active else None)
    return Result(
        allowed=True,
        backend="redis",
        retry_after=0,
        limit=tightest.limit if tightest is not None else 0,
        remaining=max(_int(raw[3]), 0),
        window=tightest.name if tightest is not None else "",
        reset_after=0,
    )


def wait_seconds(identity: str, policy: str, windows: Sequence[Window]) -> float | None:
    """Take one slot; return ``0.0`` when admitted, else seconds to wait.

    ``None`` when Redis did not answer. A denial is **not** consumed (the script
    commits only when every window admits), so a blocking caller may sleep for
    the returned interval and retry. Milliseconds are preserved — unlike
    :func:`consume`, which reports whole ``Retry-After`` seconds — because the
    Bedrock limiter runs a one-second window and a whole-second hint would make
    it wait a full second for a slot that frees in a few milliseconds.
    """
    active = [window for window in windows if window.limit > 0 and window.seconds > 0]
    if not identity or not active:
        return None
    keys = [key(identity, policy, window) for window in active]
    args: list[int] = []
    for window in active:
        args.extend([window.limit, window.window_ms])
    raw = redis_client.run(CONSUME_SCRIPT, _CONSUME, keys=keys, args=args)
    if not isinstance(raw, (list, tuple)) or len(raw) < 7:
        return None
    if _int(raw[0]) == 1:
        return 0.0
    return max(_int(raw[1]), 0) / 1000.0


def gcra_reset_hint() -> int:
    """``Retry-After`` fallback when the denying window could not be identified."""
    try:
        return max(int(os.environ.get("RATELIMIT_DEFAULT_RETRY_AFTER_SECONDS", "60")), 1)
    except (TypeError, ValueError):
        return 60


def peek(identity: str, policy: str, windows: Sequence[Window]) -> list[tuple[int, int]] | None:
    """Per-window ``(remaining, retry_after_seconds)``. ``None`` when no Redis."""
    active = [window for window in windows if window.limit > 0 and window.seconds > 0]
    if not identity or not active:
        return None
    keys = [key(identity, policy, window) for window in active]
    args: list[int] = []
    for window in active:
        args.extend([window.limit, window.window_ms])
    raw = redis_client.run(PEEK_SCRIPT, _PEEK, keys=keys, args=args)
    if not isinstance(raw, (list, tuple)) or len(raw) < len(active) * 2:
        return None
    out: list[tuple[int, int]] = []
    for index in range(len(active)):
        remaining = max(_int(raw[index * 2]), 0)
        retry = max(_int(raw[index * 2 + 1]), 0)
        out.append((remaining, (retry + 999) // 1000 if retry else 0))
    return out
