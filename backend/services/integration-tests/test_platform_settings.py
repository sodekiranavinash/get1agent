"""Platform settings + per-user network usage (moto-backed DynamoDB)."""

from __future__ import annotations

from core import network, ratelimit
from data.repositories import platform, quotas

USER = "u_7k3f9qz2mpx8n4rq"


def test_network_flag_defaults_on() -> None:
    settings = platform.get_settings()
    assert settings["networkToolsEnabled"] is True
    assert network.enabled() is True


def test_set_network_flag_round_trips() -> None:
    updated = platform.set_network_tools_enabled(False, updated_by="admin@example.com")
    assert updated["networkToolsEnabled"] is False
    assert updated["updatedBy"] == "admin@example.com"
    assert network.enabled() is False

    platform.set_network_tools_enabled(True, updated_by="admin@example.com")
    assert network.enabled() is True


def test_network_usage_counters() -> None:
    assert quotas.get_network_usage(USER) == {"runs": 0, "lastRunAt": None}
    quotas.record_network_run(USER)
    quotas.record_network_run(USER)
    usage = quotas.get_network_usage(USER)
    assert usage["runs"] == 2
    assert usage["lastRunAt"]


def test_ratelimit_current_window() -> None:
    assert ratelimit.current(USER, kind="custom-tools") == 0
    assert ratelimit.allow(USER, kind="custom-tools", limit=2) is True
    assert ratelimit.current(USER, kind="custom-tools") == 1
    assert ratelimit.allow(USER, kind="custom-tools", limit=2) is True
    assert ratelimit.allow(USER, kind="custom-tools", limit=2) is False


def test_network_describe_shape() -> None:
    described = network.describe()
    for key in (
        "enabled",
        "windowSeconds",
        "limitPerWindow",
        "maxConnectionsPerRun",
        "execTimeoutSeconds",
        "testExecTimeoutSeconds",
    ):
        assert key in described
