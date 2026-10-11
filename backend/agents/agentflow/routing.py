"""Automatic model routing — the ``auto`` model.

When an agent or a workflow is configured with ``model="auto"`` the user has
declined to pick a model, so the runtime chooses one for the run **before** the
question is executed and uses that model for the whole run.

The choice is made with the Strands Agents SDK's model-routing primitives
(``ClassifierStrategy``): a small, fast Bedrock model reads the latest user
request plus a capability profile for every platform model, then selects the
least capable candidate that can still deliver a complete and accurate result —
so routine requests land on the cheap/fast models and reasoning, coding or
very-long/multimodal requests escalate.

The decision is resolved *up front* rather than by handing a live ``ModelRouter``
to the agent. That matters here: the host needs to know the selected model
before it runs so the id is streamed to the client, the correct context window is
used by the context meter and summarizer, and the right price is charged. The
router's own docs note that a live router leaves ``agent.model`` on the first
candidate for context estimation, which would be wrong for a mixed candidate
set.

Routing is best-effort: any classifier failure/timeout falls back to
:data:`agentflow.models.DEFAULT_MODEL` and never fails the run.
"""

from __future__ import annotations

import json
import os
from typing import Any

from agentflow.config import RuntimeConfig
from agentflow.models import (
    AUTO_MODEL,
    DEFAULT_MODEL,
    SUPPORTED_MODELS,
    build_model,
    is_auto_model,
    resolve_model_id,
)

# Capability evidence handed to the classifier. Every platform model must have a
# profile; ``name`` is the display label, ``description``/``metadata`` are the
# evidence the classifier reasons over. Keep it compact — the SDK bounds the
# aggregate serialized evidence — and never put secrets here (it crosses a
# provider boundary).
MODEL_PROFILES: dict[str, dict[str, Any]] = {
    "zai.glm-4.7-flash": {
        "name": "GLM 4.7 Flash",
        "description": "Cheapest and fastest general-purpose model with tool use.",
        "metadata": {
            "cost": "lowest",
            "latency": "lowest",
            "context": "128k",
            "strengths": "everyday questions, knowledge search, summarization, simple tool calls",
            "weaknesses": "hard multi-step reasoning, coding, very long inputs",
        },
    },
    "nvidia.nemotron-nano-3-30b": {
        "name": "Nemotron Nano 3 30B",
        "description": "Very fast everyday model with tool use.",
        "metadata": {
            "cost": "low",
            "latency": "very_low",
            "context": "128k",
            "strengths": "fast everyday tasks, light reasoning, tool calling",
            "weaknesses": "hard reasoning, coding, very long inputs",
        },
    },
    "deepseek.v3.2": {
        "name": "DeepSeek V3.2",
        "description": "Strong reasoning and coding model.",
        "metadata": {
            "cost": "high",
            "latency": "medium",
            "context": "128k",
            "strengths": "coding, mathematics, hard multi-step reasoning, careful analysis",
            "weaknesses": "cost, latency; simple requests do not need it",
        },
    },
    "qwen.qwen3-next-80b-a3b": {
        "name": "Qwen3 Next 80B",
        "description": "Balanced multilingual model with tool use.",
        "metadata": {
            "cost": "medium",
            "latency": "medium",
            "context": "128k",
            "strengths": "balanced quality, multilingual, moderate reasoning",
            "weaknesses": "more expensive than the fast models for routine work",
        },
    },
    "global.amazon.nova-2-lite-v1:0": {
        "name": "Nova 2 Lite",
        "description": "Large-context multimodal model.",
        "metadata": {
            "cost": "medium",
            "latency": "medium",
            "context": "1M",
            "strengths": "very long documents and inputs, images and multimodal content, large-context synthesis",
            "weaknesses": "overkill for short text-only requests",
        },
    },
}

# Routing policy. The SDK appends its own isolation/validity/structured-output
# rules, so this only sets the cost/quality trade-off.
DEFAULT_ROUTING_POLICY = (
    "You route one request to the single best platform model. First identify the "
    "request's hard requirements — input size, images or multimodal content, "
    "coding, and multi-step reasoning — and rule out any candidate whose "
    "evidence shows it cannot meet them. Among the remaining candidates choose "
    "the cheapest and fastest one that can still deliver a complete and accurate "
    "result. Reserve the strongest reasoning model for coding or genuinely hard "
    "multi-step reasoning, and the large-context model for very long or "
    "multimodal inputs. Do not infer quality or preference from candidate order."
)

# Classifier model that makes the routing decision. A small/fast Bedrock model is
# enough; it is called once per routed run.
DEFAULT_ROUTER_MODEL = DEFAULT_MODEL


def routing_enabled() -> bool:
    """Whether ``auto`` routing is active (``AGENT_MODEL_ROUTING``, default on)."""
    value = (os.environ.get("AGENT_MODEL_ROUTING", "true") or "true").strip().lower()
    return value not in ("0", "false", "no", "off", "none", "")


def router_model_id() -> str:
    """The model used to classify the request (``AGENT_ROUTER_MODEL``)."""
    configured = (os.environ.get("AGENT_ROUTER_MODEL") or "").strip()
    return resolve_model_id(configured or DEFAULT_ROUTER_MODEL)


def router_timeout_seconds() -> float:
    """Maximum seconds to wait for the routing decision."""
    try:
        value = float(os.environ.get("AGENT_ROUTER_TIMEOUT_SECONDS") or "20")
    except ValueError:
        return 20.0
    return value if 0 < value < float("inf") else 20.0


def routing_policy() -> str:
    """The classifier's routing policy (``AGENT_ROUTER_POLICY``)."""
    return (os.environ.get("AGENT_ROUTER_POLICY") or "").strip() or DEFAULT_ROUTING_POLICY


def _warn(message: str, error: Exception) -> None:
    print(
        json.dumps(
            {
                "level": "warning",
                "message": message,
                "errorType": type(error).__name__,
                "error": str(error),
            }
        ),
        flush=True,
    )


def _candidates(config: RuntimeConfig) -> tuple[Any, ...]:
    """Build one routing candidate per platform model with its capability profile."""
    from strands.models import RoutingCandidate

    candidates: list[Any] = []
    for model_id in SUPPORTED_MODELS:
        profile = MODEL_PROFILES.get(model_id, {})
        candidates.append(
            RoutingCandidate(
                model=build_model(config, model_id, guardrail=None),
                name=model_id,
                description=profile.get("description") or model_id,
                metadata=profile.get("metadata") or {},
            )
        )
    return tuple(candidates)


async def choose_model(
    config: RuntimeConfig,
    request_text: str,
    agent_prompt: str | None = None,
    *,
    candidates: tuple[Any, ...] | None = None,
) -> str:
    """Choose a platform model for one run, falling back to the default.

    ``request_text`` is the latest user request (only the latest request-bearing
    message is classified). ``agent_prompt`` is the agent's instructions, passed
    to the classifier as evidence about the work — never as routing instructions.
    """
    text = (request_text or "").strip()
    if not text:
        return DEFAULT_MODEL
    if not routing_enabled():
        return DEFAULT_MODEL

    try:
        from strands.models import ClassifierStrategy, RoutingContext
    except Exception as error:  # noqa: BLE001 - routing is optional
        _warn("Model routing unavailable; using the default model", error)
        return DEFAULT_MODEL

    try:
        routing_candidates = candidates if candidates is not None else _candidates(config)
        classifier = build_model(config, router_model_id(), guardrail=None)
        strategy = ClassifierStrategy(
            classifier,
            system_prompt=routing_policy(),
            timeout=router_timeout_seconds(),
        )
        context = RoutingContext(
            messages=[{"role": "user", "content": [{"text": text}]}],
            system_prompt=(agent_prompt or "").strip() or None,
            tool_specs=[],
            candidates=routing_candidates,
            invocation_state={},
        )
        selected = await strategy.select(context)
    except Exception as error:  # noqa: BLE001 - a routing failure must not fail the run
        _warn("Model routing failed; using the default model", error)
        return DEFAULT_MODEL

    if selected is not None and selected.name in SUPPORTED_MODELS:
        return str(selected.name)
    return DEFAULT_MODEL


__all__ = [
    "AUTO_MODEL",
    "DEFAULT_ROUTING_POLICY",
    "MODEL_PROFILES",
    "choose_model",
    "is_auto_model",
    "router_model_id",
    "router_timeout_seconds",
    "routing_enabled",
    "routing_policy",
]
