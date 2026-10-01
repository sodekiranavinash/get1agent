"""Deterministic retrieval metrics + aggregation.

The retrieval leg mirrors the Ragas convention: a golden case may carry
``expectedSources`` (a list of ``{documentId, page?}``); when it does, we score
the retrieved chunks as a set against the relevant set. When a case has no
expected sources those metrics are simply omitted (not zeroed) so the run
aggregates stay honest.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from . import config


def _round(value: float) -> float:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return 0.0


def _expected_ref(source: dict[str, Any]) -> tuple[str, Any]:
    return (str(source.get("documentId") or ""), source.get("page"))


def _retrieved_ref(chunk: dict[str, Any]) -> tuple[str, Any]:
    return (str(chunk.get("documentId") or ""), chunk.get("page"))


def _matches(expected: tuple[str, Any], retrieved: tuple[str, Any]) -> bool:
    """A page-less expected source matches any page of the same document."""
    exp_doc, exp_page = expected
    got_doc, got_page = retrieved
    if exp_doc != got_doc:
        return False
    if exp_page in (None, ""):
        return True
    return exp_page == got_page


def retrieval_metrics(
    chunks: list[dict[str, Any]], expected_sources: list[dict[str, Any]] | None
) -> dict[str, float]:
    """Set-based retrieval metrics over the returned chunks (rank order)."""
    if not expected_sources:
        return {}
    expected = [_expected_ref(source) for source in expected_sources]
    retrieved = [_retrieved_ref(chunk) for chunk in chunks]

    matched_expected: set[int] = set()
    matched_retrieved: set[int] = set()
    first_relevant_rank = 0
    for rank, ref in enumerate(retrieved, start=1):
        for index, exp in enumerate(expected):
            if index in matched_expected:
                continue
            if _matches(exp, ref):
                matched_expected.add(index)
                matched_retrieved.add(rank - 1)
                if not first_relevant_rank:
                    first_relevant_rank = rank
                break

    recall = len(matched_expected) / len(expected) if expected else 0.0
    precision = len(matched_retrieved) / len(retrieved) if retrieved else 0.0
    hit_rate = 1.0 if matched_expected else 0.0
    mrr = 1.0 / first_relevant_rank if first_relevant_rank else 0.0
    return {
        "context_recall": _round(recall),
        "context_precision": _round(precision),
        "hit_rate": _round(hit_rate),
        "mrr": _round(mrr),
    }


def trajectory_metrics(
    actual_tools: list[str] | None, expected_tools: list[str] | None
) -> dict[str, float]:
    """Order-insensitive tool-use precision/recall/F1 + the number of calls."""
    actual = [str(name).strip() for name in (actual_tools or []) if str(name).strip()]
    result: dict[str, float] = {"tool_calls": float(len(actual))}
    expected = [str(name).strip() for name in (expected_tools or []) if str(name).strip()]
    if expected:
        overlap = sum((Counter(actual) & Counter(expected)).values())
        precision = overlap / len(actual) if actual else 0.0
        recall = overlap / len(expected)
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        result.update(
            {
                "tool_precision": _round(precision),
                "tool_recall": _round(recall),
                "tool_f1": _round(f1),
            }
        )
    return result


def aggregate_metrics(metric_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Average every numeric metric present, plus per-metric case counts."""
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for row in metric_rows:
        for name, value in row.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            totals[name] = totals.get(name, 0.0) + float(value)
            counts[name] = counts.get(name, 0) + 1

    aggregate: dict[str, Any] = {}
    for name in config.ALL_METRICS:
        if counts.get(name):
            aggregate[name] = _round(totals[name] / counts[name])
            aggregate[f"{name}_cases"] = counts[name]
    return aggregate
