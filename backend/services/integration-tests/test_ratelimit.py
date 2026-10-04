"""Global Bedrock rate limiter (DynamoDB window counter)."""

from __future__ import annotations

from core import ratelimit_bedrock as rl


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
    calls = {"n": 0}

    def fake_consume(*args, **kwargs):
        calls["n"] += 1
        return calls["n"] >= 3

    monkeypatch.setattr(rl, "_consume", fake_consume)
    monkeypatch.setattr(rl.time, "sleep", lambda _seconds: None)

    rl.throttle("m")

    assert calls["n"] == 3
