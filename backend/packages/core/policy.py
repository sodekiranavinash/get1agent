"""Deterministic tool-call policy (AgentCore Policy).

Prompt instructions are advisory; this is enforcement. Every tool call the agent
runtime is about to make is passed to :func:`build_evaluator`, which returns
``(allowed, reason)``. Denials are surfaced to the model as an error result so it
can adapt.

The decision is made by **AgentCore Policy** (a managed policy engine). This
module owns the engine id and the small, unit-testable local policy surface:
always-denied tools (``AGENT_POLICY_DENY_TOOLS``) and an optional allowlist
(``AGENT_POLICY_ALLOW_TOOLS``). ``AGENT_POLICY_MODE`` selects ``enforce`` (the
default — denials block the call) or ``report`` (log only), which is intended for
staging a new rule, never steady-state production.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

Guard = Callable[[str, dict[str, Any]], tuple[bool, str]]

# Tools that reach the network or run code — the highest-value ones to govern.
NETWORK_TOOLS = ("web-search", "http-fetch", "browser")
CODE_TOOLS = ("code-interpreter",)


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def engine() -> str:
    return _env("AGENT_POLICY_ENGINE")


def enabled() -> bool:
    return bool(engine())


def mode() -> str:
    return (_env("AGENT_POLICY_MODE", "enforce") or "enforce").lower()


def _csv(name: str) -> list[str]:
    raw = _env(name)
    return [part.strip() for part in raw.split(",") if part.strip()]


def denied_tools() -> list[str]:
    return _csv("AGENT_POLICY_DENY_TOOLS")


def allowed_tools() -> list[str]:
    return _csv("AGENT_POLICY_ALLOW_TOOLS")


def build_evaluator() -> Guard | None:
    """Return the guard for this run, or None when no engine is configured."""
    if not enabled():
        return None

    deny = set(denied_tools())
    allow = set(allowed_tools())

    def evaluate(tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        name = str(tool_name or "").strip()
        if not name:
            return False, "tool name is required"
        if name in deny:
            return False, f'tool "{name}" is denied by policy'
        if allow and name not in allow:
            return False, f'tool "{name}" is not in the allowed set'
        if not isinstance(arguments, dict):
            return False, "tool arguments must be an object"
        return True, ""

    return evaluate


def evaluate_or_report(
    tool_name: str, arguments: dict[str, Any], guard: Guard
) -> tuple[bool, str]:
    """Apply ``guard`` honoring ``AGENT_POLICY_MODE=report`` (never blocks)."""
    allowed, reason = guard(tool_name, arguments)
    if allowed or mode() == "enforce":
        return allowed, reason
    print(
        json.dumps(
            {
                "level": "warning",
                "message": "policy would deny tool call (report mode)",
                "tool": tool_name,
                "reason": reason,
            }
        ),
        flush=True,
    )
    return True, ""
