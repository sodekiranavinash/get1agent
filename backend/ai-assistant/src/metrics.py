"""AI Assistant telemetry — CloudWatch metrics via Embedded Metric Format (EMF).

Every AI Assistant turn emits one EMF line, which CloudWatch turns into metrics with no
``PutMetricData`` call and no IAM permission: the numbers arrive as structured
logs. This is the same mechanism the platform's run feedback already uses.

What is measured is deliberately the set of things that would make AI Assistant worse
without anyone noticing:

* **latency** — first token and total, because a widget that feels slow is dead;
* **cost** — tokens in/out and USD, split by guest and signed-in;
* **classifier** — how often a question needed a model, the rules-stage share,
  and how often the classifier failed open (a silent quality lever);
* **refusals** — how often AI Assistant declined, which is the number that says whether
  the nudge is too aggressive.

A metrics failure must never affect an answer, so every function swallows
errors.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from core import usage as core_usage

NAMESPACE = os.environ.get("AI_ASSISTANT_METRIC_NAMESPACE", "get1agent/ai-assistant")


def cost_micro_usd(model: str, tokens_in: int, tokens_out: int) -> int:
    """Attributed cost in integer micro-USD.

    Delegates to the platform's own pricing table (``core.usage``) so AI Assistant's cost
    numbers match the billing the product already shows — the model catalogue,
    prices and credits must never disagree about what a token costs.
    """
    try:
        return int(core_usage.cost_micro_usd(model, tokens_in, tokens_out))
    except Exception:  # noqa: BLE001 - an unpriced model reports no cost
        return 0


def _emit(payload: dict[str, Any]) -> None:
    try:
        print(json.dumps(payload, default=str, ensure_ascii=False), flush=True)
    except Exception:  # noqa: BLE001 - metrics must never break a turn
        pass


def turn(
    *,
    surface: str,
    model: str,
    intent_kind: str,
    intent_stage: str,
    latency_ms: int,
    ttft_ms: int | None,
    tokens_in: int,
    tokens_out: int,
    source_count: int,
    tool_calls: int,
    refused: bool,
    failed: bool = False,
    classifier_latency_ms: int | None = None,
) -> dict[str, Any]:
    """Emit the per-turn metric line.

    ``surface`` is ``guest`` or ``user``: the two are split because they have
    different limits and a different acceptable cost profile.
    """
    cost = cost_micro_usd(model, tokens_in, tokens_out)
    dimensions = [["surface"]]
    metrics = [
        {"Name": "Turns", "Unit": "Count"},
        {"Name": "LatencyMs", "Unit": "Milliseconds"},
        {"Name": "TokensIn", "Unit": "Count"},
        {"Name": "TokensOut", "Unit": "Count"},
        {"Name": "CostMicroUsd", "Unit": "None"},
    ]
    if ttft_ms is not None:
        metrics.append({"Name": "TimeToFirstTokenMs", "Unit": "Milliseconds"})
    if classifier_latency_ms is not None:
        metrics.append({"Name": "ClassifierMs", "Unit": "Milliseconds"})

    payload: dict[str, Any] = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": NAMESPACE,
                    "Dimensions": dimensions,
                    "Metrics": metrics,
                }
            ],
        },
        "surface": surface if surface in ("guest", "user") else "user",
        "model": model,
        "intentKind": intent_kind,
        "intentStage": intent_stage,
        "Turns": 1,
        "LatencyMs": int(latency_ms),
        "TokensIn": int(tokens_in),
        "TokensOut": int(tokens_out),
        "CostMicroUsd": cost,
        "SourceCount": int(source_count),
        "ToolCalls": int(tool_calls),
        "Refused": 1 if refused else 0,
        "Failed": 1 if failed else 0,
        "RulesHit": 1 if intent_stage == "rules" else 0,
        "ModelClassified": 1 if intent_stage == "model" else 0,
        "FailOpen": 1 if intent_stage in ("fallback", "rules-only") else 0,
    }
    if ttft_ms is not None:
        payload["TimeToFirstTokenMs"] = int(ttft_ms)
    if classifier_latency_ms is not None:
        payload["ClassifierMs"] = int(classifier_latency_ms)

    _emit(payload)
    return payload


def retrieval(diagnostic: dict[str, Any], *, surface: str) -> dict[str, Any]:
    """Emit one retrieval diagnostic line (cache hits are the cost story)."""
    payload = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": NAMESPACE,
                    "Dimensions": [["surface"]],
                    "Metrics": [
                        {"Name": "Retrievals", "Unit": "Count"},
                        {"Name": "RetrievalMs", "Unit": "Milliseconds"},
                        {"Name": "CacheHits", "Unit": "Count"},
                    ],
                }
            ],
        },
        "surface": surface if surface in ("guest", "user") else "user",
        "stage": str(diagnostic.get("stage") or ""),
        "Retrievals": 1,
        "RetrievalMs": int(diagnostic.get("latencyMs") or 0),
        "CacheHits": 1 if diagnostic.get("stage") == "cache-hit" else 0,
        "Returned": int(diagnostic.get("returned") or 0),
    }
    _emit(payload)
    return payload


def rate_limited(*, surface: str, scope: str) -> None:
    """Emit a throttle event so a limit can be tuned from data, not guesswork."""
    _emit(
        {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": NAMESPACE,
                        "Dimensions": [["surface", "scope"]],
                        "Metrics": [{"Name": "RateLimited", "Unit": "Count"}],
                    }
                ],
            },
            "surface": surface if surface in ("guest", "user") else "user",
            "scope": scope,
            "RateLimited": 1,
        }
    )
