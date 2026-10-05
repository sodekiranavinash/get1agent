"""Environment-driven configuration for the custom-tools sandbox and limits."""

from __future__ import annotations

import os

from core.sandbox import SandboxConfig
from core.sandbox import agentcore

DEFAULT_EXEC_TIMEOUT = 90
DEFAULT_TEST_EXEC_TIMEOUT = 180
DEFAULT_MAX_CONNECTIONS = 25
DEFAULT_RUNS_PER_HOUR = 60
DEFAULT_MAX_CODE_BYTES = 65_536
DEFAULT_MAX_OUTPUT = 50_000
DEFAULT_MAX_RESULT_CHARS = 20_000


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


def sandbox_config() -> SandboxConfig:
    return SandboxConfig(
        mode=_env("CUSTOM_TOOLS_MODE", "agentcore").lower(),
        identifier=_env("CUSTOM_TOOLS_IDENTIFIER", agentcore.DEFAULT_IDENTIFIER),
        region=_env("CUSTOM_TOOLS_REGION") or _env("AWS_REGION") or "ap-south-1",
        table=_env("CUSTOM_TOOLS_SESSIONS_TABLE") or _env("DYNAMODB_TABLE"),
        session_ttl=_env_int("CUSTOM_TOOLS_SESSION_TIMEOUT_SECONDS", 900),
        exec_timeout=_env_int("CUSTOM_TOOLS_EXEC_TIMEOUT_SECONDS", DEFAULT_EXEC_TIMEOUT),
        max_sessions=max(_env_int("CUSTOM_TOOLS_MAX_SESSIONS_PER_USER", 1), 1),
        max_code_bytes=_env_int("CUSTOM_TOOLS_MAX_CODE_BYTES", DEFAULT_MAX_CODE_BYTES),
        max_output=_env_int("CUSTOM_TOOLS_MAX_OUTPUT_CHARS", DEFAULT_MAX_OUTPUT),
        thread_prefix="CTOOLCONV#",
        session_name_prefix="ct-",
        # MCP Builder tools may call the public internet (HTTP(S)). Outbound
        # connections are capped per run and private/reserved destinations are
        # refused by the sandbox guard.
        allow_network=_env_bool("CUSTOM_TOOLS_ALLOW_NETWORK", True),
        max_connections=max(
            _env_int("CUSTOM_TOOLS_MAX_CONNECTIONS", DEFAULT_MAX_CONNECTIONS), 1
        ),
    )


def test_exec_timeout() -> int:
    """Wall-clock budget for an MCP Builder test run (longer than a real call)."""
    return _env_int("CUSTOM_TOOLS_TEST_EXEC_TIMEOUT_SECONDS", DEFAULT_TEST_EXEC_TIMEOUT)


def runs_per_hour() -> int:
    """Network-enabled custom-tool runs allowed per user per hour."""
    return max(_env_int("CUSTOM_TOOLS_RUNS_PER_HOUR", DEFAULT_RUNS_PER_HOUR), 1)


def max_result_chars() -> int:
    return _env_int("CUSTOM_TOOLS_MAX_RESULT_CHARS", DEFAULT_MAX_RESULT_CHARS)


def blocked_modules() -> str:
    return _env("CUSTOM_TOOLS_BLOCKED_MODULES") or _env("BLOCKED_MODULES")


def allowed_modules() -> str:
    return _env("CUSTOM_TOOLS_ALLOWED_MODULES") or _env("ALLOWED_MODULES")
