"""Amazon Bedrock cost/latency levers: prompt caching, service tiers, routing.

Central place the runtime and Labs read these from, so the knobs are in one spot:

* **Prompt caching** — cache the repeated prefix (system prompt + tool schemas).
* **Service tiers** — ``flex`` is ~50% cheaper for non-time-sensitive work
  (ingestion, evals); ``priority`` is faster at a premium.
* **Intelligent Prompt Routing** — one endpoint that routes within a model family
  (e.g. Nova Pro ↔ Nova Lite) to the cheapest model that can answer well.
* **Application Inference Profiles** — route a workload through its own profile so
  the bill is attributable per feature (chat / eval / ingestion).

All are env-driven and default to safe values, so nothing changes unless set.

Env:
``BEDROCK_PROMPT_CACHE`` (auto|anthropic|off), ``BEDROCK_PROMPT_CACHE_TTL`` (5m|1h),
``BEDROCK_SERVICE_TIER`` (standard|flex|priority),
``BEDROCK_PROMPT_ROUTER_ARN`` (intelligent prompt router ARN),
``BEDROCK_PROFILE_CHAT`` / ``_EVAL`` / ``_INGESTION`` (application inference profile
ARNs; when set, the model id is replaced by the profile ARN).
"""

from __future__ import annotations

import os
from typing import Any

# Default Bedrock prompt routers (family endpoints) usable as a modelId.
DEFAULT_ROUTERS = {
    "amazon": "amazon.nova-premier-v1:0",  # replaced by the router ARN when set
    "anthropic": "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "meta": "meta.llama3-3-70b-instruct-v1:0",
}

WORKLOADS = ("chat", "eval", "ingestion")


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def prompt_cache() -> dict[str, Any] | None:
    """``{"strategy", "ttl"}`` for prompt caching, or None when disabled."""
    mode = (_env("BEDROCK_PROMPT_CACHE", "auto") or "auto").lower()
    if mode in ("0", "false", "no", "off", "none"):
        return None
    return {
        "strategy": mode,
        "ttl": _env("BEDROCK_PROMPT_CACHE_TTL") or None,
    }


def service_tier() -> str | None:
    tier = _env("BEDROCK_SERVICE_TIER").lower()
    return tier if tier in ("standard", "flex", "priority") else None


def prompt_router_arn() -> str:
    """The intelligent prompt router ARN, or empty when routing is off."""
    return _env("BEDROCK_PROMPT_ROUTER_ARN")


def routing_enabled() -> bool:
    return bool(prompt_router_arn())


def application_profile(workload: str) -> str:
    """The application inference profile ARN for a workload, or empty."""
    key = f"BEDROCK_PROFILE_{workload.strip().upper()}"
    return _env(key)


def resolve_model(model_id: str, *, workload: str = "chat") -> str:
    """Apply routing + application profiles to a model id.

    Order: an application inference profile for the workload wins (per-feature
    billing), then an intelligent prompt router (cost routing), then the model.
    """
    profile = application_profile(workload)
    if profile:
        return profile
    if routing_enabled():
        return prompt_router_arn()
    return model_id


def describe() -> dict[str, Any]:
    return {
        "promptCache": prompt_cache(),
        "serviceTier": service_tier(),
        "promptRouterArn": prompt_router_arn() or None,
        "applicationProfiles": {
            workload: application_profile(workload) or None for workload in WORKLOADS
        },
    }
