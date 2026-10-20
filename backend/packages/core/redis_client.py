"""Shared, best-effort Redis client (rate limiting + caches).

Redis is **optional infrastructure**. Every other backend on the platform is a
managed AWS service; this module is the one deliberate exception (Redis Cloud /
ElastiCache / MemoryDB reachable over public TLS), and it exists so the
request-path work that is currently a DynamoDB round trip — the per-identity
rate limiter, the query-embedding cache, the semantic cache — can be answered
from memory instead.

Two rules shape everything here:

* **Redis may never make a request slower or fail one.** The socket timeouts are
  deliberately short (sub-second), the connection pool is tiny, and a **circuit
  breaker** stops re-paying a dead endpoint's timeout: after
  ``REDIS_BREAKER_FAILURES`` consecutive failures the client reports
  unavailable for ``REDIS_BREAKER_COOLDOWN_SECONDS`` so callers fall back to
  their DynamoDB path immediately. Callers treat ``None`` from
  :func:`run` as "Redis did not answer" and degrade — they never raise.
* **The URL is a secret.** It is read from ``REDIS_URL``, or fetched once per
  container from SSM Parameter Store (``REDIS_URL_SSM_PARAM``, decrypted) and
  cached in-process, so a password never sits in a Lambda environment variable.

Everything is namespaced with ``REDIS_PREFIX`` (default ``g1a:``) so one
database can be shared by non-platform keys without collisions.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

_LOCK = threading.Lock()
_CLIENT: Any = None
_CLIENT_TARGET = ""
_IMPORT_FAILED = False
_SSM_CACHE: dict[str, str] = {}
_SCRIPTS: dict[tuple[str, str], Any] = {}

# Circuit breaker state. ``_OPEN_UNTIL`` is a monotonic deadline, not a
# timestamp, so it is immune to clock changes.
_FAILURES = 0
_OPEN_UNTIL = 0.0


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


def prefix() -> str:
    return (os.environ.get("REDIS_PREFIX") or "g1a:").strip()


def _from_ssm(param: str) -> str:
    """Fetch (and cache in-process) a SecureString parameter."""
    cached = _SSM_CACHE.get(param)
    if cached is not None:
        return cached
    try:
        import boto3

        client = boto3.client("ssm")
        raw = client.get_parameter(Name=param, WithDecryption=True)
        value = str(((raw.get("Parameter") or {}).get("Value") or "")).strip()
    except Exception:  # noqa: BLE001 - a missing parameter means "no Redis"
        return ""
    if value:
        _SSM_CACHE[param] = value
    return value


def url() -> str:
    """The configured Redis URL, or ``""`` when Redis is not configured."""
    direct = (os.environ.get("REDIS_URL") or "").strip()
    if direct:
        return direct
    param = (os.environ.get("REDIS_URL_SSM_PARAM") or "").strip()
    if param:
        return _from_ssm(param)
    return ""


def enabled() -> bool:
    return bool(url())


def _load_redis() -> Any:
    global _IMPORT_FAILED
    if _IMPORT_FAILED:
        return None
    try:
        import redis  # noqa: PLC0415 - optional dependency, imported on use
    except Exception:  # noqa: BLE001 - Lambdas without the extra stay importable
        _IMPORT_FAILED = True
        return None
    return redis


def client() -> Any:
    """A process-wide client, rebuilt only when the URL changes.

    One connection per container (``max_connections=2``) because the deployed
    Redis may cap concurrent connections well below the Lambda concurrency
    ceiling; a refused connection degrades to the fallback path instead of
    queueing a request.
    """
    global _CLIENT, _CLIENT_TARGET
    target = url()
    if not target:
        return None
    with _LOCK:
        if _CLIENT is not None and _CLIENT_TARGET == target:
            return _CLIENT
        redis = _load_redis()
        if redis is None:
            return None
        try:
            _CLIENT = redis.Redis.from_url(
                target,
                socket_timeout=_env_float("REDIS_SOCKET_TIMEOUT_SECONDS", 0.5),
                socket_connect_timeout=_env_float("REDIS_CONNECT_TIMEOUT_SECONDS", 0.5),
                # No implicit retries: a limiter/cache must fail fast and let the
                # caller use its DynamoDB path rather than block twice as long.
                retry_on_timeout=False,
                health_check_interval=_env_int("REDIS_HEALTH_CHECK_SECONDS", 30),
                decode_responses=True,
                max_connections=2,
            )
            _CLIENT_TARGET = target
        except Exception:  # noqa: BLE001 - a bad URL means "no Redis"
            _CLIENT = None
            _CLIENT_TARGET = ""
            return None
        return _CLIENT


def reset() -> None:
    """Drop cached client/script/SSM state (tests, or after a config change)."""
    global _CLIENT, _CLIENT_TARGET, _FAILURES, _OPEN_UNTIL
    with _LOCK:
        _CLIENT = None
        _CLIENT_TARGET = ""
        _SSM_CACHE.clear()
        _SCRIPTS.clear()
        _FAILURES = 0
        _OPEN_UNTIL = 0.0


# --- circuit breaker ----------------------------------------------------------


def breaker_open() -> bool:
    return time.monotonic() < _OPEN_UNTIL


def record_failure() -> None:
    global _FAILURES, _OPEN_UNTIL
    with _LOCK:
        _FAILURES += 1
        if _FAILURES >= max(_env_int("REDIS_BREAKER_FAILURES", 3), 1):
            _OPEN_UNTIL = time.monotonic() + _env_float(
                "REDIS_BREAKER_COOLDOWN_SECONDS", 30.0
            )
            _FAILURES = 0


def record_success() -> None:
    global _FAILURES, _OPEN_UNTIL
    with _LOCK:
        _FAILURES = 0
        _OPEN_UNTIL = 0.0


def available() -> bool:
    """True when Redis is configured, the breaker is closed and a client exists."""
    if not enabled() or breaker_open():
        return False
    return client() is not None


# --- scripts ------------------------------------------------------------------


def _script(name: str, lua: str) -> Any:
    redis = client()
    if redis is None:
        return None
    key = (name, _CLIENT_TARGET)
    with _LOCK:
        script = _SCRIPTS.get(key)
        if script is None:
            script = redis.register_script(lua)
            _SCRIPTS[key] = script
        return script


def run(name: str, lua: str, *, keys: list[str], args: list[Any]) -> Any:
    """Run a Lua script atomically. ``None`` when Redis did not answer.

    ``None`` is *not* an error: every caller is expected to treat it as "Redis is
    unavailable, use the fallback". Only genuine cheap failures reach here —
    configuration gaps return ``None`` without touching the network.
    """
    if not available():
        return None
    script = _script(name, lua)
    if script is None:
        return None
    try:
        result = script(keys=keys, args=args)
    except Exception:  # noqa: BLE001 - fall back, never raise into a request
        record_failure()
        return None
    record_success()
    return result


def command(name: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run one plain command (``GET``/``SET``/``PING``/…) with the breaker.

    Used by the non-Lua paths (exact cache, health probe). Same contract as
    :func:`run`: ``None`` means "Redis did not answer".
    """
    if not available():
        return None
    redis = client()
    if redis is None:
        return None
    try:
        result = getattr(redis, fn)(*args, **kwargs)
    except Exception:  # noqa: BLE001
        record_failure()
        return None
    record_success()
    return result


def health() -> dict[str, Any]:
    """Best-effort health snapshot for the admin and usage pages."""
    target = url()
    report: dict[str, Any] = {
        "configured": bool(target),
        "reachable": False,
        "breakerOpen": breaker_open(),
        "prefix": prefix(),
        "latencyMs": None,
        "error": "",
    }
    if not target:
        return report
    if breaker_open():
        report["error"] = "circuit breaker open"
        return report
    redis = client()
    if redis is None:
        report["error"] = "client unavailable"
        return report
    started = time.perf_counter()
    try:
        redis.ping()
    except Exception as exc:  # noqa: BLE001
        record_failure()
        report["error"] = f"{type(exc).__name__}: {exc}"
        return report
    record_success()
    report["reachable"] = True
    report["latencyMs"] = round((time.perf_counter() - started) * 1000, 2)
    return report
