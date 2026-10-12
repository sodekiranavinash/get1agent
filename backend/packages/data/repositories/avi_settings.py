"""Avi settings — the admin-controlled configuration for the in-product assistant.

One small item (``PLATFORM#SETTINGS`` / ``#AVI``) holds every Avi knob: the kill
switch, the guest toggle, the four model ids and the rate limits. It is separate
from the ``#FLAGS`` item (network tools) so each concern writes only its own
attributes and neither can clobber the other.

Why an item and not env vars: the admin → Avi page must be able to change the
model or a limit and have it take effect **without a redeploy**. The services
read this through :func:`get_settings`, which is best-effort and cached for
:data:`CACHE_TTL_SECONDS` so a busy widget does not turn every turn into an extra
strongly-consistent read.

Defaults live in code (below) and are identical to the Terraform/Avi service
defaults, so a freshly deployed platform behaves correctly before any admin ever
opens the page.
"""

from __future__ import annotations

import os
import time
from typing import Any

from data.client import now_iso, table

PLATFORM_PK = "PLATFORM#SETTINGS"
AVI_SK = "#AVI"

# --- defaults -----------------------------------------------------------------

DEFAULT_ENABLED = True
DEFAULT_GUEST_ENABLED = True

#: Default answer model. Benchmarked fastest first token (220 ms) with correct
#: answers on the platform question set — see docs/design/avi-assistant.md.
DEFAULT_MODEL = "nvidia.nemotron-nano-3-30b"
#: Default intent classifier. Lowest-variance latency of the invocable models and
#: already the platform's planner/generator model.
DEFAULT_CLASSIFIER_MODEL = "zai.glm-4.7-flash"
#: Used only for `how_to` questions that need reasoning.
DEFAULT_REASONING_MODEL = "deepseek.v3.2"
#: Evaluations judge — deliberately never the model under test.
DEFAULT_JUDGE_MODEL = "amazon.nova-2-lite-v1:0"

DEFAULT_MAX_AGENT_STEPS = 6
DEFAULT_MAX_INPUT_CHARS = 2_000
DEFAULT_MAX_HISTORY_TURNS = 8
DEFAULT_MAX_HISTORY_CHARS = 24_000

#: Signed-in users are effectively unlimited, but bounded so a leaked token
#: cannot run up an unbounded Bedrock bill.
DEFAULT_USER_PER_HOUR = 120
DEFAULT_USER_PER_DAY = 1_000
#: Guests share an unauthenticated surface, so they are capped hard per IP hash.
DEFAULT_GUEST_PER_HOUR = 6
DEFAULT_GUEST_PER_DAY = 20

#: Bedrock models the admin page offers for each role. Every id here was probed
#: as **invocable** in this account (ap-south-1) — notably the plain
#: ``amazon.nova-*`` ids are NOT, only the ``global.`` inference profile.
MODEL_CHOICES: tuple[dict[str, Any], ...] = (
    {
        "id": "nvidia.nemotron-nano-3-30b",
        "label": "Nemotron Nano 3 30B",
        "ttftMs": 220,
        "note": "Fastest first token · default answer model",
        "roles": ("agent", "classifier"),
    },
    {
        "id": "zai.glm-4.7-flash",
        "label": "GLM 4.7 Flash",
        "ttftMs": 322,
        "note": "Cheapest and steadiest · platform planner/generator",
        "roles": ("agent", "classifier"),
    },
    {
        "id": "qwen.qwen3-next-80b-a3b",
        "label": "Qwen3 Next 80B A3B",
        "ttftMs": 378,
        "note": "Stronger reasoning, moderate latency",
        "roles": ("agent", "classifier", "reasoning"),
    },
    {
        "id": "deepseek.v3.2",
        "label": "DeepSeek V3.2",
        "ttftMs": 463,
        "note": "Escalation model for how-to reasoning",
        "roles": ("agent", "reasoning", "judge"),
    },
    {
        "id": "global.amazon.nova-2-lite-v1:0",
        "label": "Nova 2 Lite (global)",
        "ttftMs": 787,
        "note": "1M context, multimodal · default judge",
        "roles": ("agent", "judge"),
    },
)

#: Env overrides let a deployment pin a default without touching the item.
_ENV_KEYS = {
    "enabled": "AVI_ENABLED",
    "guestEnabled": "AVI_GUEST_ENABLED",
    "model": "AVI_MODEL",
    "classifierModel": "AVI_CLASSIFIER_MODEL",
    "reasoningModel": "AVI_REASONING_MODEL",
    "judgeModel": "AVI_JUDGE_MODEL",
    "maxAgentSteps": "AVI_MAX_AGENT_STEPS",
    "maxInputChars": "AVI_MAX_INPUT_CHARS",
    "userPerHour": "AVI_PER_HOUR",
    "userPerDay": "AVI_PER_DAY",
    "guestPerHour": "AVI_GUEST_PER_HOUR",
    "guestPerDay": "AVI_GUEST_PER_DAY",
}

_DEFAULTS: dict[str, Any] = {
    "enabled": DEFAULT_ENABLED,
    "guestEnabled": DEFAULT_GUEST_ENABLED,
    "model": DEFAULT_MODEL,
    "classifierModel": DEFAULT_CLASSIFIER_MODEL,
    "reasoningModel": DEFAULT_REASONING_MODEL,
    "judgeModel": DEFAULT_JUDGE_MODEL,
    "maxAgentSteps": DEFAULT_MAX_AGENT_STEPS,
    "maxInputChars": DEFAULT_MAX_INPUT_CHARS,
    "userPerHour": DEFAULT_USER_PER_HOUR,
    "userPerDay": DEFAULT_USER_PER_DAY,
    "guestPerHour": DEFAULT_GUEST_PER_HOUR,
    "guestPerDay": DEFAULT_GUEST_PER_DAY,
}

FIELDS: tuple[str, ...] = tuple(_DEFAULTS)

#: Process-local cache. Short: an admin toggle should feel immediate, but a busy
#: dialog must not add a read per token either.
CACHE_TTL_SECONDS = float(os.environ.get("AVI_SETTINGS_TTL_SECONDS") or "30")

_cache: tuple[float, dict[str, Any]] | None = None


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)


def _coerce_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _env_default(field: str, fallback: Any) -> Any:
    raw = os.environ.get(_ENV_KEYS[field])
    if raw is None or str(raw).strip() == "":
        return fallback
    if isinstance(fallback, bool):
        return _coerce_bool(raw, fallback)
    if isinstance(fallback, int):
        return _coerce_int(raw, fallback, minimum=0, maximum=1_000_000)
    return str(raw)


def defaults() -> dict[str, Any]:
    """The effective defaults (code, overridden by env when set)."""
    return {field: _env_default(field, fallback) for field, fallback in _DEFAULTS.items()}


def normalize(item: dict[str, Any] | None) -> dict[str, Any]:
    """Merge a stored item over the defaults, coercing every type."""
    base = defaults()
    stored = item or {}
    return {
        "enabled": _coerce_bool(stored.get("enabled"), base["enabled"]),
        "guestEnabled": _coerce_bool(stored.get("guestEnabled"), base["guestEnabled"]),
        "model": str(stored.get("model") or base["model"]),
        "classifierModel": str(stored.get("classifierModel") or base["classifierModel"]),
        "reasoningModel": str(stored.get("reasoningModel") or base["reasoningModel"]),
        "judgeModel": str(stored.get("judgeModel") or base["judgeModel"]),
        "maxAgentSteps": _coerce_int(
            stored.get("maxAgentSteps"), base["maxAgentSteps"], minimum=1, maximum=20
        ),
        "maxInputChars": _coerce_int(
            stored.get("maxInputChars"), base["maxInputChars"], minimum=100, maximum=20_000
        ),
        "userPerHour": _coerce_int(
            stored.get("userPerHour"), base["userPerHour"], minimum=0, maximum=100_000
        ),
        "userPerDay": _coerce_int(
            stored.get("userPerDay"), base["userPerDay"], minimum=0, maximum=100_000
        ),
        "guestPerHour": _coerce_int(
            stored.get("guestPerHour"), base["guestPerHour"], minimum=0, maximum=10_000
        ),
        "guestPerDay": _coerce_int(
            stored.get("guestPerDay"), base["guestPerDay"], minimum=0, maximum=10_000
        ),
    }


def _get_item() -> dict[str, Any]:
    return table().get_item(Key={"pk": PLATFORM_PK, "sk": AVI_SK}).get("Item") or {}


def get_settings(*, use_cache: bool = True) -> dict[str, Any]:
    """The live Avi config with defaults applied.

    Best-effort: a DynamoDB failure returns the defaults rather than breaking the
    widget (the same posture as :mod:`data.repositories.platform`).
    """
    global _cache

    now = time.monotonic()
    if use_cache and _cache and now - _cache[0] < CACHE_TTL_SECONDS:
        return dict(_cache[1])

    try:
        settings = normalize(_get_item())
    except Exception:  # noqa: BLE001 - never break a turn on a settings read
        return defaults()

    _cache = (now, settings)
    return dict(settings)


def invalidate_cache() -> None:
    """Drop the process-local cache (tests; also after an admin write)."""
    global _cache
    _cache = None


def update_settings(
    patch: dict[str, Any], *, updated_by: str = ""
) -> dict[str, Any]:
    """Admin action: persist a partial Avi config and return the new settings.

    Only known fields are written, so an unknown key cannot add attributes to the
    item. Values are normalized against the defaults before being stored, which
    keeps the item readable even if a client sends junk.
    """
    unknown = sorted(set(patch) - set(FIELDS))
    if unknown:
        raise ValueError(f"unknown Avi setting(s): {', '.join(unknown)}")

    merged = normalize({**get_settings(use_cache=False), **patch})
    timestamp = now_iso()

    # Explicit name -> placeholder map; the two bookkeeping fields use :by/:t so
    # every placeholder is supplied (an unbound placeholder is a DynamoDB error).
    assignments: list[tuple[str, str, Any]] = [
        ("updatedBy", ":by", str(updated_by or "")),
        ("updatedAt", ":t", timestamp),
    ]
    for field in FIELDS:
        assignments.append((field, f":{field}", merged[field]))

    table().update_item(
        Key={"pk": PLATFORM_PK, "sk": AVI_SK},
        UpdateExpression="SET " + ", ".join(
            f"{name} = {placeholder}" for name, placeholder, _ in assignments
        ),
        ExpressionAttributeValues={
            placeholder: value for _, placeholder, value in assignments
        },
    )
    invalidate_cache()
    return merged


def is_enabled() -> bool:
    """Whether Avi is on (the kill switch, checked on both ingress paths)."""
    return bool(get_settings().get("enabled"))


def guest_enabled() -> bool:
    """Whether unauthenticated callers may use Avi."""
    return is_enabled() and bool(get_settings().get("guestEnabled"))


def snapshot() -> dict[str, Any]:
    """The admin view: live values, effective defaults and the model catalogue."""
    stored = _get_item()
    return {
        "settings": normalize(stored),
        "defaults": defaults(),
        "modelChoices": [dict(choice) for choice in MODEL_CHOICES],
        "updatedAt": stored.get("updatedAt"),
        "updatedBy": stored.get("updatedBy"),
    }
