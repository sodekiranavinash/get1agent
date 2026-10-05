"""Platform-wide gate + limits for user tools that reach the public internet.

The MCP Builder lets user-built tools call web APIs from a network-enabled
sandbox. This module is the single place that answers two questions:

* **Is network access allowed at all?** — an admin kill switch stored in the
  platform settings item (``data.repositories.platform``). Fail-open: if the
  flag cannot be read, network stays enabled so a transient DynamoDB error does
  not silently neuter every tool.
* **What are the limits?** — the env-driven knobs shared with the custom-tools
  sandbox config (rates, connection cap, timeouts), so the Usage and admin
  surfaces can report the exact values in force.

Every read is best-effort and never raises.
"""

from __future__ import annotations

import os

DEFAULT_RUNS_PER_HOUR = 60
DEFAULT_MAX_CONNECTIONS = 25
DEFAULT_EXEC_TIMEOUT = 90
DEFAULT_TEST_EXEC_TIMEOUT = 180
WINDOW_SECONDS = 3600


def _int(name: str, default: int) -> int:
    try:
        return int((os.environ.get(name) or "").strip() or default)
    except (TypeError, ValueError):
        return default


def enabled() -> bool:
    """True when admins allow user tools to reach the public internet."""
    try:
        from data.repositories import platform

        return platform.network_tools_enabled()
    except Exception:  # noqa: BLE001 - fail open
        return True


def runs_per_hour() -> int:
    return max(_int("CUSTOM_TOOLS_RUNS_PER_HOUR", DEFAULT_RUNS_PER_HOUR), 1)


def max_connections() -> int:
    return max(_int("CUSTOM_TOOLS_MAX_CONNECTIONS", DEFAULT_MAX_CONNECTIONS), 1)


def exec_timeout() -> int:
    return _int("CUSTOM_TOOLS_EXEC_TIMEOUT_SECONDS", DEFAULT_EXEC_TIMEOUT)


def test_exec_timeout() -> int:
    return _int("CUSTOM_TOOLS_TEST_EXEC_TIMEOUT_SECONDS", DEFAULT_TEST_EXEC_TIMEOUT)


def describe(*, enabled_override: bool | None = None) -> dict[str, object]:
    """The effective network policy, for the Usage and admin surfaces."""
    return {
        "enabled": enabled() if enabled_override is None else bool(enabled_override),
        "windowSeconds": WINDOW_SECONDS,
        "limitPerWindow": runs_per_hour(),
        "maxConnectionsPerRun": max_connections(),
        "execTimeoutSeconds": exec_timeout(),
        "testExecTimeoutSeconds": test_exec_timeout(),
    }
