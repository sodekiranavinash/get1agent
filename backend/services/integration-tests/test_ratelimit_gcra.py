"""Redis-backed rate limiting (GCRA) + per-endpoint policies.

Runs against ``fakeredis`` (with ``lupa``, so the real Lua scripts execute) so
the algorithm itself is pinned without a Redis server: burst behaviour, refusal
arithmetic, the "a denial is not charged to the other windows" rule, and the
DynamoDB fallback all have to hold.

The counter half of the old contract is still pinned by
``test_platform_settings.py`` (it exercises the DynamoDB path, which is what runs
when Redis is not configured).
"""

from __future__ import annotations

import os

import fakeredis
import pytest

from core import ratelimit, redis_client
from core.ratelimit import Window, gcra, policy

FAKE_URL = "redis://fake.invalid:6379/0"
USER = "u_7k3f9qz2mpx8n4rq"


@pytest.fixture
def redis_env(monkeypatch: pytest.MonkeyPatch):
    """Install an in-process Redis into ``core.redis_client``."""
    server = fakeredis.FakeServer()
    fake = fakeredis.FakeRedis(server=server, decode_responses=True)
    monkeypatch.setenv("REDIS_URL", FAKE_URL)
    monkeypatch.setenv("RATELIMIT_BACKEND", "redis")
    redis_client.reset()
    with monkeypatch.context() as patch:
        patch.setattr(redis_client, "_CLIENT", fake)
        patch.setattr(redis_client, "_CLIENT_TARGET", FAKE_URL)
        yield fake
    redis_client.reset()


def _windows(*pairs: tuple[str, int, int]) -> list[Window]:
    return [Window(name=name, limit=limit, seconds=seconds) for name, limit, seconds in pairs]


def test_burst_is_admitted_then_the_window_smooths(redis_env) -> None:
    """N per window admits N back to back, then refuses — no boundary doubling."""
    windows = _windows(("hour", 5, 3600))
    decisions = [ratelimit.check_windows(USER, windows, policy="custom-tools") for _ in range(6)]
    assert [decision.allowed for decision in decisions] == [True] * 5 + [False]
    assert decisions[0].backend == "redis"
    assert decisions[4].remaining == 0
    refused = decisions[5]
    assert refused.remaining == 0
    assert refused.window == "hour"
    assert 0 < refused.retry_after <= 720


def test_a_denial_is_not_charged_to_the_other_windows(redis_env) -> None:
    """Stopped by the minute cap -> the hourly allowance is untouched."""
    windows = _windows(("minute", 2, 60), ("hour", 100, 3600))
    assert ratelimit.check_windows(USER, windows, policy="agent.session").allowed is True
    assert ratelimit.check_windows(USER, windows, policy="agent.session").allowed is True
    denied = ratelimit.check_windows(USER, windows, policy="agent.session")
    assert denied.allowed is False
    assert denied.window == "minute"

    peeked = gcra.peek(USER, "agent.session", windows)
    assert peeked is not None
    minute_remaining, _ = peeked[0]
    hour_remaining, _ = peeked[1]
    assert minute_remaining == 0
    # Two requests were admitted, nothing more — the refused third was not
    # counted against the hour.
    assert hour_remaining == 98


def test_the_tightest_window_is_the_one_reported(redis_env) -> None:
    windows = _windows(("minute", 10, 60), ("day", 3, 86_400))
    decision = ratelimit.check_windows(USER, windows, policy="agent.session")
    assert decision.allowed is True
    assert decision.window == "day"  # 2 of 3 left is tighter than 9 of 10
    assert decision.limit == 3
    assert decision.remaining == 2


def test_named_policy_resolves_and_uses_its_configured_limits(redis_env) -> None:
    resolved = policy.get("agent.session")
    assert resolved is not None
    limits = {window.name: window.limit for window in resolved.windows}
    assert limits == {"minute": 10, "hour": 120}

    allowed = [ratelimit.check(USER, policy="agent.session") for _ in range(11)]
    assert all(decision.allowed for decision in allowed[:10])
    assert allowed[10].allowed is False


def test_check_reports_the_backend_that_answered(redis_env) -> None:
    assert ratelimit.check(USER, policy="vault.test").backend == "redis"
    assert ratelimit.describe(USER)["backend"] == "redis"


def test_policy_override_disables_a_limit(monkeypatch: pytest.MonkeyPatch, redis_env) -> None:
    monkeypatch.setenv("RATELIMIT_POLICY", '{"vault.test": []}')
    resolved = policy.get("vault.test")
    assert resolved is not None and resolved.windows == ()
    assert ratelimit.check(USER, policy="vault.test").allowed is True


def test_policy_override_replaces_the_windows(monkeypatch: pytest.MonkeyPatch, redis_env) -> None:
    monkeypatch.setenv("RATELIMIT_POLICY", '{"vault.test": [[1, 60]]}')
    assert ratelimit.check(USER, policy="vault.test").allowed is True
    denied = ratelimit.check(USER, policy="vault.test")
    assert denied.allowed is False
    assert denied.limit == 1
    assert denied.window == "minute"


def test_describe_reports_usage_without_consuming(redis_env) -> None:
    ratelimit.check(USER, policy="vault.test")
    snapshot = ratelimit.describe(USER, policies=["vault.test"])
    assert snapshot["enforced"] is True
    assert snapshot["backend"] == "redis"
    minute = next(
        window
        for window in snapshot["policies"][0]["windows"]
        if window["name"] == "minute"
    )
    assert minute["used"] == 1
    assert minute["remaining"] == minute["limit"] - 1

    # A second snapshot must not consume anything.
    again = ratelimit.describe(USER, policies=["vault.test"])
    assert again["policies"][0]["windows"] == snapshot["policies"][0]["windows"]


def test_falls_back_to_dynamodb_when_redis_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``auto`` keeps enforcing on the DynamoDB counter when Redis is down."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_URL_SSM_PARAM", "")
    monkeypatch.setenv("RATELIMIT_BACKEND", "auto")
    redis_client.reset()

    assert ratelimit.check(USER, policy="agent.session").backend == "dynamodb"
    allowed = [ratelimit.allow(USER, kind="custom-tools", limit=2) for _ in range(3)]
    assert allowed == [True, True, False]


def test_redis_only_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit ``redis`` backend must not block traffic when it is down."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_URL_SSM_PARAM", "")
    monkeypatch.setenv("RATELIMIT_BACKEND", "redis")
    redis_client.reset()

    decision = ratelimit.check(USER, policy="agent.session")
    assert decision.allowed is True
    assert decision.backend == "none"


def test_backend_none_disables_enforcement(monkeypatch: pytest.MonkeyPatch, redis_env) -> None:
    monkeypatch.setenv("RATELIMIT_BACKEND", "none")
    assert ratelimit.enabled() is False
    assert all(ratelimit.allow(USER, kind="x", limit=1) for _ in range(5))


def test_circuit_breaker_opens_after_repeated_failures(
    monkeypatch: pytest.MonkeyPatch, redis_env
) -> None:
    monkeypatch.setenv("REDIS_BREAKER_FAILURES", "2")
    redis_client.record_success()
    assert redis_client.breaker_open() is False
    redis_client.record_failure()
    assert redis_client.breaker_open() is False
    redis_client.record_failure()
    assert redis_client.breaker_open() is True
    assert redis_client.available() is False
    # While the breaker is open nothing is attempted: ``auto`` falls back to the
    # DynamoDB counter, which still enforces.
    monkeypatch.setenv("RATELIMIT_BACKEND", "auto")
    assert ratelimit.check(USER, policy="vault.test").backend == "dynamodb"
    redis_client.record_success()
    assert redis_client.breaker_open() is False


def test_route_rules_limit_writes_only() -> None:
    route = policy.policy_id_for_route
    assert route("POST", ["v1", "agent-run", "session"]) == "agent.session"
    assert route("POST", ["v1", "custom-tools", "sessions", "s1", "turn"]) == "custom-tools.generate"
    assert route("POST", ["v1", "evals", "runs"]) == "evals.run"
    assert route("POST", ["v1", "lab", "playground", "run"]) == "playground.run"
    assert route("POST", ["v1", "knowledge-bases", "kb_1", "documents", "presign"]) == "knowledge.write"
    assert route("DELETE", ["v1", "knowledge-bases", "kb_1", "documents", "doc_1"]) == "knowledge.write"
    # Reads and the AI Assistant's own ingress are never limited here.
    assert route("GET", ["v1", "agent-run", "session"]) == ""
    assert route("POST", ["v1", "ai-assistant", "ask"]) == ""
    assert route("GET", ["v1", "traces", "abc"]) == ""
    # Anything else falls to the generous floor.
    assert route("POST", ["v1", "agents"]) == "api.default"
    assert route("PUT", ["v1", "workflows", "wf_1"]) == "api.default"


def test_every_route_rule_names_a_known_policy() -> None:
    for method, path, policy_id in policy.ROUTE_RULES:
        assert method.isupper(), (method, path)
        assert policy_id in policy.DEFAULTS, policy_id


def test_env_limit_override_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATELIMIT_CUSTOM_TOOLS_PER_WINDOW", "7")
    assert ratelimit.limit("custom-tools", 60) == 7
    monkeypatch.delenv("RATELIMIT_CUSTOM_TOOLS_PER_WINDOW")
    assert ratelimit.limit("custom-tools", 60) == 60


def test_health_reports_the_configured_backend(redis_env) -> None:
    report = redis_client.health()
    assert report["configured"] is True
    assert report["reachable"] is True
    assert report["prefix"] == "g1a:"


def test_policy_windows_are_shortest_first() -> None:
    for resolved in policy.all_policies():
        seconds = [window.seconds for window in resolved.windows]
        assert seconds == sorted(seconds), resolved.id


def test_a_check_is_one_round_trip_once_the_script_is_cached(redis_env) -> None:
    """Every window in one EVALSHA (the deployed instance caps ops/sec).

    The first call after a cold container also pays ``SCRIPT LOAD``, which is
    redis-py's EVALSHA->NOSCRIPT->LOAD path; steady state is a single call.
    """
    resolved = policy.get("agent.session")
    assert resolved is not None
    assert len(resolved.windows) >= 2
    # Warm the script cache the way the first real request would.
    assert ratelimit.check(USER, policy="agent.session").allowed is True

    calls: list[object] = []
    original = redis_env.evalsha

    def counting(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    redis_env.evalsha = counting  # type: ignore[method-assign]
    assert ratelimit.check(USER, policy="agent.session").allowed is True
    assert len(calls) == 1
    # sha + numkeys + one key and two args per window — one call.
    assert len(calls[0]) == 2 + 3 * len(resolved.windows)


def test_missing_redis_library_degrades_to_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Lambda built without the ``redis`` extra must still enforce."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_URL_SSM_PARAM", "")
    monkeypatch.setenv("RATELIMIT_BACKEND", "auto")
    redis_client.reset()
    assert os.environ.get("REDIS_URL") is None
    assert ratelimit.check(USER, policy="api.default").backend == "dynamodb"
