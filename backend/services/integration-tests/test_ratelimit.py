"""Global Bedrock rate limiter (Redis GCRA first, DynamoDB window counter fallback)."""

from __future__ import annotations

import time

import fakeredis
import pytest

from core import ratelimit_bedrock as rl
from core import redis_client

FAKE_URL = "redis://fake.invalid:6379/0"


@pytest.fixture
def redis_env(monkeypatch: pytest.MonkeyPatch):
    """Install an in-process Redis (real Lua via lupa) into ``core.redis_client``."""
    fake = fakeredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    monkeypatch.setenv("REDIS_URL", FAKE_URL)
    monkeypatch.setenv("RATELIMIT_BACKEND", "redis")
    monkeypatch.setenv("BEDROCK_RATELIMIT_BACKEND", "redis")
    redis_client.reset()
    with monkeypatch.context() as patch:
        patch.setattr(redis_client, "_CLIENT", fake)
        patch.setattr(redis_client, "_CLIENT_TARGET", FAKE_URL)
        yield fake
    redis_client.reset()


class _FakeTable:
    def __init__(self) -> None:
        self.counts: dict[tuple[str, str], int] = {}

    def update_item(self, Key, **kwargs):
        key = (Key["pk"], Key["sk"])
        self.counts[key] = self.counts.get(key, 0) + 1
        return {"Attributes": {"n": self.counts[key]}}


def _clear_env(monkeypatch) -> None:
    for name in (
        "BEDROCK_RATELIMIT_RPM",
        "BEDROCK_RATELIMIT_RPM_MAP",
        "BEDROCK_RATELIMIT_RPM_M",
    ):
        monkeypatch.delenv(name, raising=False)


def test_rpm_default_and_env(monkeypatch) -> None:
    _clear_env(monkeypatch)
    assert rl.rpm("amazon.titan-embed-text-v2:0") == 60

    monkeypatch.setenv("BEDROCK_RATELIMIT_RPM", "120")
    assert rl.rpm("anything") == 120

    monkeypatch.setenv("BEDROCK_RATELIMIT_RPM_MAP", '{"m": 100}')
    assert rl.rpm("m") == 100
    assert rl.rpm("other") == 120


def test_per_window_is_ceil(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("BEDROCK_RATELIMIT_RPM_MAP", '{"a": 60, "b": 100}')
    assert rl._per_window("a") == 1
    assert rl._per_window("b") == 2


def test_consume_enforces_limit(monkeypatch) -> None:
    table = _FakeTable()
    import data.client

    monkeypatch.setattr(data.client, "table", lambda: table)

    assert rl._consume("m", 100, 2) is True
    assert rl._consume("m", 100, 2) is True
    assert rl._consume("m", 100, 2) is False  # 3rd request in the same window


def test_throttle_noop_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("BEDROCK_RATELIMIT_ENABLED", "false")
    called = {"n": 0}

    def fake_consume(*args, **kwargs):
        called["n"] += 1
        return True

    monkeypatch.setattr(rl, "_consume", fake_consume)

    rl.throttle()

    assert called["n"] == 0


def test_throttle_retries_until_slot(monkeypatch) -> None:
    monkeypatch.setenv("BEDROCK_RATELIMIT_ENABLED", "true")
    monkeypatch.setenv("DYNAMODB_TABLE", "get1agent")
    # Force the DynamoDB path so the original counter behaviour is pinned.
    monkeypatch.setenv("BEDROCK_RATELIMIT_BACKEND", "dynamodb")
    calls = {"n": 0}

    def fake_consume(*args, **kwargs):
        calls["n"] += 1
        return calls["n"] >= 3

    monkeypatch.setattr(rl, "_consume", fake_consume)
    monkeypatch.setattr(rl.time, "sleep", lambda _seconds: None)

    rl.throttle("m")

    assert calls["n"] == 3


# --- Redis backend ------------------------------------------------------------


def test_backend_falls_back_to_ratelimit_backend(monkeypatch) -> None:
    monkeypatch.delenv("BEDROCK_RATELIMIT_BACKEND", raising=False)
    monkeypatch.setenv("RATELIMIT_BACKEND", "dynamodb")
    assert rl.backend() == "dynamodb"
    monkeypatch.setenv("BEDROCK_RATELIMIT_BACKEND", "redis")
    assert rl.backend() == "redis"


def test_redis_wait_admits_then_reports_the_exact_wait(redis_env) -> None:
    """GCRA reports sub-second precision — the whole point of using it here."""
    window = rl._window("m", 1)
    assert rl._redis_wait("m", window) == 0.0
    waited = rl._redis_wait("m", window)
    assert waited is not None
    assert 0.0 < waited <= 1.0


def test_throttle_uses_redis_and_returns_immediately_when_admitted(
    redis_env, monkeypatch
) -> None:
    monkeypatch.setenv("BEDROCK_RATELIMIT_RPM_MAP", '{"m": 120}')  # 2 per second
    slept: list[float] = []
    monkeypatch.setattr(rl.time, "sleep", lambda seconds: slept.append(seconds))

    rl.throttle("m")

    assert slept == []
    assert rl.enabled() is True


def test_throttle_waits_for_the_next_redis_slot(redis_env, monkeypatch) -> None:
    monkeypatch.setenv("BEDROCK_RATELIMIT_RPM_MAP", '{"m": 60}')  # 1 per second
    slept: list[float] = []
    real_sleep = time.sleep
    monkeypatch.setattr(
        rl.time, "sleep", lambda seconds: (slept.append(seconds), real_sleep(seconds))[1]
    )

    rl.throttle("m")  # admitted straight away
    assert slept == []
    # The window is now full, and GCRA reports the exact wait for the next slot.
    assert 0.0 < rl._redis_wait("m", rl._window("m", 1)) <= 1.0

    rl.throttle("m")  # the window is full: it must sleep, then admit
    assert slept, "the second call should have waited for the next second"
    assert max(slept) <= 0.3  # sleeps in short increments, not a whole second


def test_enabled_when_only_redis_is_configured(redis_env, monkeypatch) -> None:
    monkeypatch.delenv("DYNAMODB_TABLE", raising=False)
    assert rl.enabled() is True


def test_missing_redis_falls_back_to_the_dynamodb_counter(monkeypatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_URL_SSM_PARAM", "")
    monkeypatch.setenv("RATELIMIT_BACKEND", "auto")
    monkeypatch.setenv("BEDROCK_RATELIMIT_ENABLED", "true")
    monkeypatch.setenv("DYNAMODB_TABLE", "get1agent")
    redis_client.reset()

    assert rl._redis_wait("m", rl._window("m", 1)) is None
    assert rl.enabled() is True  # the DynamoDB table keeps it enforcing
