"""Runtime configuration for the AI Assistant services.

Two layers, on purpose:

* **Deployment config** (env vars) — the reserved retrieval scope, model region,
    limits that must exist before DynamoDB is reachable. These are Terraform's.
* **Live config** (the admin item, ``PLATFORM#SETTINGS`` / ``#AI_ASSISTANT``) — the kill
    switch, the model ids and the rate limits, editable from admin → AI Assistant at
    runtime with no redeploy. Read through :mod:`data.repositories.ai_assistant_settings`,
    which caches for 30 s and fails back to the code defaults.

Nothing here reads the user's request, so it is safe to call from both ingress
paths and from the guest Lambda (which has no per-user state at all).
"""

from __future__ import annotations

import os
from typing import Any

from data.repositories import ai_assistant_settings


def retrieval_scope() -> str:
    """The reserved scope AI Assistant retrieves from (``platform`` by default).

    Its S3 keys, vector index (``idx-platform``) and knowledge-base item all hang
    off this id, so changing it points AI Assistant at a different corpus without code
    changes.
    """
    return str(
        os.environ.get("AI_ASSISTANT_SCOPE")
        or os.environ.get("AI_ASSISTANT_PLATFORM_USER_ID")
        or "platform"
    ).strip()


def platform_kb_id() -> str:
    return str(os.environ.get("AI_ASSISTANT_KB_ID") or "kb_platform_docs_0001").strip()


def model() -> str:
    """The answer model, live-editable from the admin page."""
    return str(live().get("model") or ai_assistant_settings.DEFAULT_MODEL)


def classifier_model() -> str:
    return str(live().get("classifierModel") or ai_assistant_settings.DEFAULT_CLASSIFIER_MODEL)


def reasoning_model() -> str:
    return str(live().get("reasoningModel") or ai_assistant_settings.DEFAULT_REASONING_MODEL)


def judge_model() -> str:
    return str(live().get("judgeModel") or ai_assistant_settings.DEFAULT_JUDGE_MODEL)


def max_agent_steps() -> int:
    return int(live().get("maxAgentSteps") or ai_assistant_settings.DEFAULT_MAX_AGENT_STEPS)


def max_input_chars() -> int:
    return int(live().get("maxInputChars") or ai_assistant_settings.DEFAULT_MAX_INPUT_CHARS)


def max_history_turns() -> int:
    return int(
        os.environ.get("AI_ASSISTANT_MAX_HISTORY_TURNS")
        or ai_assistant_settings.DEFAULT_MAX_HISTORY_TURNS
    )


def max_history_chars() -> int:
    return int(
        os.environ.get("AI_ASSISTANT_MAX_HISTORY_CHARS")
        or ai_assistant_settings.DEFAULT_MAX_HISTORY_CHARS
    )


def enabled() -> bool:
    return bool(live().get("enabled", True))


def guest_enabled() -> bool:
    return bool(live().get("guestEnabled", True)) and enabled()


def region() -> str:
    return str(
        os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "ap-south-1"
    )


def live(*, use_cache: bool = True) -> dict[str, Any]:
    """The live admin config (defaults applied, cached ~30 s, fail-open)."""
    return ai_assistant_settings.get_settings(use_cache=use_cache)


def snapshot() -> dict[str, Any]:
    """What ``/ping`` and the admin page report as the effective configuration."""
    return {
        "enabled": enabled(),
        "guestEnabled": guest_enabled(),
        "model": model(),
        "classifierModel": classifier_model(),
        "reasoningModel": reasoning_model(),
        "judgeModel": judge_model(),
        "maxAgentSteps": max_agent_steps(),
        "maxInputChars": max_input_chars(),
        "scope": retrieval_scope(),
        "kbId": platform_kb_id(),
        "region": region(),
    }
