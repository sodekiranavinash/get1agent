"""AgentCore Optimization helper (phase A7).

Optimization consumes evaluation results: **Insights** (failure/intent/trajectory
analysis over many sessions) and **Recommendations** (auto-generated system-prompt
and tool-description improvements), validated by batch eval / A/B.

Insights and Recommendations are free during preview and are driven from the
console/API rather than per-run code, so this module's job is to surface the
*status* and the *inputs* the platform must provide (evaluated traces). It is the
single place the UI asks "is optimization available, and what did it suggest?".

Config: ``AGENT_OPTIMIZATION_ENABLED``, ``AGENT_OPTIMIZATION_INSIGHTS_ARN``.
"""

from __future__ import annotations

import os
from typing import Any


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def enabled() -> bool:
    return (_env("AGENT_OPTIMIZATION_ENABLED", "false") or "false").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def insights_arn() -> str:
    return _env("AGENT_OPTIMIZATION_INSIGHTS_ARN")


def region() -> str:
    return _env("BEDROCK_REGION") or _env("AWS_REGION") or "ap-south-1"


def recommendation_targets() -> list[str]:
    """Configuration surfaces Optimization may rewrite (kept explicit/audited)."""
    return ["system_prompt", "tool_descriptions"]


def describe() -> dict[str, Any]:
    return {
        "configured": enabled(),
        "insightsArn": insights_arn() or None,
        "region": region(),
        "targets": recommendation_targets(),
        "note": (
            "Optimization analyzes AgentCore Evaluations results; it is not a "
            "per-run service."
        ),
    }
