"""Build the Strands model for the agent runtime.

The platform gateway is **Amazon Bedrock** (Amazon Nova plus third-party models
hosted on Bedrock), so the default client is Strands' ``BedrockModel`` (SigV4,
converse/invoke under the hood). A user may instead run on their **own**
OpenAI-compatible provider set in the Vault, which switches to ``OpenAIModel``.

Keep ``SUPPORTED_MODELS`` in sync with ``SUPPORTED_AGENT_MODELS`` in
``backend/services/apis/user-api/handler.py`` and ``AGENT_MODELS`` in the frontend.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from agentflow.config import RuntimeConfig

# Curated Bedrock models, cheapest/fastest first. The 1M-context multimodal
# Nova 2 Lite uses the global cross-region inference profile (not in-region).
DEFAULT_MODEL = "zai.glm-4.7-flash"
SUPPORTED_MODELS = (
    "zai.glm-4.7-flash",
    "nvidia.nemotron-nano-3-30b",
    "deepseek.v3.2",
    "qwen.qwen3-next-80b-a3b",
    "global.amazon.nova-2-lite-v1:0",
)

CLIENT_USER_AGENT = "get1agent/1.0"

# Sentinel: ``build_model`` keeps the env-configured guardrail when the caller
# does not pass one, but an explicit ``None`` means "no guardrail" (opt-out).
_GUARDRAIL_UNSET = object()

# Context window (tokens) per model, used for the context meter and to trigger
# proactive summarization before a call would overflow. Override any of them with
# ``AGENT_CONTEXT_WINDOW_<MODEL_ID_UPPER_SNAKE>`` or the whole default with
# ``AGENT_CONTEXT_WINDOW``.
DEFAULT_CONTEXT_WINDOW = int(os.environ.get("AGENT_CONTEXT_WINDOW") or "128000")
_CONTEXT_WINDOWS: dict[str, int] = {
    "zai.glm-4.7-flash": 128_000,
    "nvidia.nemotron-nano-3-30b": 128_000,
    "deepseek.v3.2": 128_000,
    "qwen.qwen3-next-80b-a3b": 128_000,
    "global.amazon.nova-2-lite-v1:0": 1_000_000,
}


def context_window_limit(model_id: str) -> int:
    override = os.environ.get(
        "AGENT_CONTEXT_WINDOW_" + re.sub(r"[^A-Za-z0-9]+", "_", model_id).upper()
    )
    if override and override.isdigit():
        return int(override)
    return _CONTEXT_WINDOWS.get(model_id, DEFAULT_CONTEXT_WINDOW)


def resolve_model_id(model_id: str | None) -> str:
    """Return a supported Bedrock model, falling back for legacy/unknown ids."""
    model = (model_id or "").strip()
    if model in SUPPORTED_MODELS:
        return model
    if model:
        print(
            json.dumps(
                {
                    "level": "warning",
                    "message": "Unsupported agent model; falling back",
                    "requested": model,
                    "using": DEFAULT_MODEL,
                }
            ),
            flush=True,
        )
    return DEFAULT_MODEL


def cache_config() -> Any | None:
    """Bedrock prompt-caching config, or None when disabled.

    ``AGENT_PROMPT_CACHE=auto`` (the default) lets Strands inject cache points
    where the model supports them, so the system prompt + tool schemas are billed
    at the discounted cache-read rate on later turns. Set ``off`` to disable, or
    ``anthropic`` to force the Anthropic format. ``AGENT_PROMPT_CACHE_TTL`` sets
    the cache TTL (e.g. ``1h``; Bedrock requires non-increasing TTLs).
    """
    mode = (os.environ.get("AGENT_PROMPT_CACHE", "auto") or "auto").strip().lower()
    if mode in ("0", "false", "no", "off", "none"):
        return None
    try:
        from strands.models.model import CacheConfig, CacheToolsConfig

        ttl = (os.environ.get("AGENT_PROMPT_CACHE_TTL") or "").strip() or None
        return CacheConfig(
            strategy=mode,
            ttl=ttl,
            tools_ttl=CacheToolsConfig(type="default", ttl=ttl),
        )
    except Exception:  # noqa: BLE001 - older SDKs: fall back to no caching
        return None


def service_tier() -> str | None:
    """Bedrock service tier for the call (``flex`` is 50% cheaper, ``priority``
    has a premium). Unset leaves the model's default (standard) tier."""
    tier = (os.environ.get("AGENT_SERVICE_TIER") or "").strip().lower()
    return tier if tier in ("standard", "flex", "priority") else None


def build_model(
    config: RuntimeConfig,
    model_id: str,
    session_id: str | None = None,
    provider: dict[str, Any] | None = None,
    guardrail: Any = _GUARDRAIL_UNSET,
) -> Any:
    """Build a Strands model.

    ``provider`` (from :mod:`agentflow.provider`) switches to the user's own
    OpenAI-compatible endpoint instead of the platform Bedrock gateway. (A guardrail
    cannot be applied to a third-party OpenAI endpoint; it is ignored there.)

    ``guardrail`` is a resolved ``{"id", "version"}`` from
    :func:`agentflow.guardrails.resolve_guardrail`. When omitted the model falls
    back to the env-configured platform guardrail; an explicit ``None`` disables it.
    """
    if provider:
        from strands.models.openai import OpenAIModel

        return OpenAIModel(
            client_args={
                "api_key": provider["apiKey"],
                "base_url": provider["baseUrl"],
                "default_headers": {"user-agent": CLIENT_USER_AGENT},
            },
            model_id=model_id,
            context_window_limit=context_window_limit(model_id),
        )

    from botocore.config import Config as BotocoreConfig
    from strands.models.bedrock import BedrockModel

    from core import guardrails

    resolved_guardrail: dict[str, Any] | None
    if guardrail is _GUARDRAIL_UNSET:
        if guardrails.enabled():
            resolved_guardrail = {
                "id": guardrails.guardrail_id(),
                "version": guardrails.guardrail_version(),
            }
        else:
            resolved_guardrail = None
    elif isinstance(guardrail, dict) and (guardrail.get("id") or "").strip():
        resolved_guardrail = guardrail
    else:
        resolved_guardrail = None

    model_kwargs: dict[str, Any] = {
        "model_id": model_id,
        "region_name": config.bedrock_region,
        "boto_client_config": BotocoreConfig(
            retries={"max_attempts": 8, "mode": "adaptive"}
        ),
    }
    if resolved_guardrail:
        model_kwargs.update(
            {
                "guardrail_id": resolved_guardrail["id"],
                "guardrail_version": resolved_guardrail.get("version")
                or guardrails.DEFAULT_GUARDRAIL_VERSION,
                "guardrail_trace": "enabled",
                # Redact a triggered input (blocking prompt) but let the model's
                # own guardrail-intervened response surface as the answer.
                "guardrail_redact_input": True,
            }
        )
    # Prompt caching: the system prompt + tool schemas are the repeated prefix on
    # every turn, so caching them cuts input cost (up to 90%) and latency.
    cache = cache_config()
    if cache is not None:
        model_kwargs["cache_config"] = cache
    tier = service_tier()
    if tier:
        model_kwargs["service_tier"] = tier
    return BedrockModel(**model_kwargs)
