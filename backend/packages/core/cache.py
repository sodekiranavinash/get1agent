"""Best-effort response cache (default: Upstash Redis over REST).

Used on the **normal request path only** (query/document embeddings and
knowledge search) — never in the Labs (Playground / Evaluations), where fresh
outputs matter.

Backend is selected by ``CACHE_BACKEND`` (default ``redis``). The Redis backend
talks to Upstash's REST API (``UPSTASH_REDIS_REST_URL`` +
``UPSTASH_REDIS_REST_TOKEN``) with ``urllib`` — no VPC, no connection pool,
nothing to keep warm. When it is not configured every call is a no-op, so local
dev and tests are unaffected. Every operation swallows errors: the cache must
never break a request.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

_TIMEOUT_SECONDS = 2.0


def backend() -> str:
    return (os.environ.get("CACHE_BACKEND") or "redis").strip().lower()


def _redis_config() -> tuple[str, str] | None:
    url = (os.environ.get("UPSTASH_REDIS_REST_URL") or "").strip().rstrip("/")
    token = (os.environ.get("UPSTASH_REDIS_REST_TOKEN") or "").strip()
    if not (url and token):
        return None
    return url, token


def enabled() -> bool:
    """True when a usable cache backend is configured."""
    if backend() == "none":
        return False
    if backend() == "redis":
        return _redis_config() is not None
    return False


def prefix() -> str:
    return (os.environ.get("CACHE_PREFIX") or "g1a:").strip()


def cache_key(kind: str, *parts: Any) -> str:
    """Deterministic key: ``<prefix><kind>:<sha256(parts)>`` (payloads hashed)."""
    digest = hashlib.sha256("\x1f".join(str(part) for part in parts).encode()).hexdigest()
    return f"{prefix()}{kind}:{digest}"


def ttl(kind: str, default: int) -> int:
    """Per-kind TTL from ``CACHE_<KIND>_TTL_SECONDS`` (0 = no expiry)."""
    raw = os.environ.get(f"CACHE_{kind.upper()}_TTL_SECONDS")
    try:
        return max(int(raw), 0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# --- low-level Upstash REST ---------------------------------------------------


def _post(path: str, payload: Any) -> Any:
    config = _redis_config()
    if config is None:
        return None
    url, token = config
    request = urllib.request.Request(
        f"{url}{path}",
        data=json.dumps(payload).encode(),
        headers={
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return json.loads(response.read() or b"[]")
    except Exception as exc:  # noqa: BLE001 - cache must never break a request
        print(f"cache unavailable: {exc!r}", file=sys.stderr)
        return None


def _command(*args: Any) -> Any:
    """Run one Redis command; returns the ``result`` (or None on failure)."""
    response = _post("", list(args))
    if isinstance(response, dict):
        return response.get("result")
    return None


def _pipeline(commands: list[list[Any]]) -> list[Any]:
    if not commands:
        return []
    response = _post("/pipeline", commands)
    if not isinstance(response, list):
        return [None] * len(commands)
    return [entry.get("result") if isinstance(entry, dict) else None for entry in response]


# --- JSON convenience ---------------------------------------------------------


def get(key: str) -> Any:
    if not enabled():
        return None
    raw = _command("GET", key)
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def set(key: str, value: Any, ttl_seconds: int) -> None:  # noqa: A001 - cache API
    if not enabled():
        return
    try:
        encoded = json.dumps(value)
    except (TypeError, ValueError):
        return
    command: list[Any] = ["SET", key, encoded]
    if ttl_seconds > 0:
        command += ["EX", ttl_seconds]
    _command(*command)


def get_many(keys: list[str]) -> list[Any]:
    if not keys or not enabled():
        return [None] * len(keys)
    results = _pipeline([["GET", key] for key in keys])
    values: list[Any] = []
    for raw in results:
        if isinstance(raw, str) and raw:
            try:
                values.append(json.loads(raw))
                continue
            except ValueError:
                pass
        values.append(None)
    return values


def set_many(pairs: list[tuple[str, Any]], ttl_seconds: int) -> None:
    if not pairs or not enabled():
        return
    commands: list[list[Any]] = []
    for key, value in pairs:
        try:
            encoded = json.dumps(value)
        except (TypeError, ValueError):
            continue
        command: list[Any] = ["SET", key, encoded]
        if ttl_seconds > 0:
            command += ["EX", ttl_seconds]
        commands.append(command)
    _pipeline(commands)
