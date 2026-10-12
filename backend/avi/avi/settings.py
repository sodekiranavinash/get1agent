"""Runtime configuration for the Avi services.

Two layers, on purpose:

* **Deployment config** (env vars) — the reserved retrieval scope, model region,
    limits that must exist before DynamoDB is reachable. These are Terraform's.
* **Live config** (the admin item, ``PLATFORM#SETTINGS`` / ``#AVI``) — the kill
    switch, the model ids and the rate limits, editable from admin → Avi at
    runtime with no redeploy. Read through :mod:`data.repositories.avi_settings`,
    which caches for 30 s and fails back to the code defaults.

Nothing here reads the user's request, so it is safe to call from both ingress
paths and from the guest Lambda (which has no per-user state at all).
"""

from __future__ import annotations

import os
from typing import Any

from data.repositories import avi_settings


def retrieval_scope() -> str:
    """The reserved scope Avi retrieves from (``platform`` by default).

    Its S3 keys, vector index (``idx-platform``) and knowledge-base item all hang
    off this id, so changing it points Avi at a different corpus without code
    changes.
    """
    return str(
        os.environ.get("AVI_SCOPE")
        or os.environ.get("AVI_PLATFORM_USER_ID")
        or "platform"
    ).strip()


def platform_kb_id() -> str:
    return str(os.environ.get("AVI_KB_ID") or "kb_platform_docs_0001").strip()


def model() -> str:
    """The answer model, live-editable from the admin page."""
    return str(live().get("model") or avi_settings.DEFAULT_MODEL)


def classifier_model() -> str:
    return str(live().get("classifierModel") or avi_settings.DEFAULT_CLASSIFIER_MODEL)


def reasoning_model() -> str:
    return str(live().get("reasoningModel") or avi_settings.DEFAULT_REASONING_MODEL)


def judge_model() -> str:
    return str(live().get("judgeModel") or avi_settings.DEFAULT_JUDGE_MODEL)


def max_agent_steps() -> int:
    return int(live().get("maxAgentSteps") or avi_settings.DEFAULT_MAX_AGENT_STEPS)


def max_input_chars() -> int:
    return int(live().get("maxInputChars") or avi_settings.DEFAULT_MAX_INPUT_CHARS)


def max_history_turns() -> int:
    return int(
        os.environ.get("AVI_MAX_HISTORY_TURNS")
        or avi_settings.DEFAULT_MAX_HISTORY_TURNS
    )


def max_history_chars() -> int:
    return int(
        os.environ.get("AVI_MAX_HISTORY_CHARS")
        or avi_settings.DEFAULT_MAX_HISTORY_CHARS
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
    return avi_settings.get_settings(use_cache=use_cache)


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
