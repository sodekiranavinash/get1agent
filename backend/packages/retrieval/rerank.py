"""Cross-encoder reranking, shared by every retrieval caller.

Two callers rerank the same way and for the same reason — RRF is a *fusion* score,
not a relevance score, so the top of a fused list is often not the best answer:

* `knowledge-mcp` reranks a user's knowledge-base search;
* AI Assistant reranks the platform-docs corpus.

They must agree, because a reranker that behaves differently in the two places
would make AI Assistant's answers inconsistent with the product's own search. So this
lives in the shared `retrieval` package rather than being copied into each service.

Two backends, selected by `RERANK_MODE`:

* **`bedrock`** (the default) — **Bedrock Rerank** (`amazon.rerank-v1:0`). That model
  is not offered in `ap-south-1`, so the call is **cross-region** to `us-west-2`
  (`RERANK_REGION` overrides).
* **`local`** — a HuggingFace TEI cross-encoder container (`POST /rerank`), used by
  the Floci stack, which does not emulate Bedrock Rerank.
* **`none`** — skip reranking entirely.

Every failure path returns the input order with `applied=False`. A search must never
fail, and must never silently reorder, because the reranker is unreachable.
"""

from __future__ import annotations

import json
import os
from typing import Any

# Bedrock Rerank is not available in ap-south-1, so reranking runs cross-region.
DEFAULT_RERANK_REGION = os.environ.get("RERANK_REGION", "us-west-2")
DEFAULT_RERANK_MODEL_ARN = os.environ.get(
    "RERANK_MODEL_ARN",
    "arn:aws:bedrock:us-west-2::foundation-model/amazon.rerank-v1:0",
)
# Local cross-encoder served by HuggingFace Text Embeddings Inference (TEI).
DEFAULT_LOCAL_RERANK_URL = os.environ.get(
    "LOCAL_RERANK_URL", "http://reranker:80/rerank"
)
LOCAL_RERANK_TIMEOUT = int(os.environ.get("LOCAL_RERANK_TIMEOUT_SECONDS", "60"))
# TEI rejects requests above the model's max batch (32 for MiniLM-L6); split.
LOCAL_RERANK_BATCH_SIZE = int(os.environ.get("LOCAL_RERANK_BATCH_SIZE", "32"))


def rerank_mode() -> str:
    """``bedrock`` (default), ``local`` (TEI) or ``none``."""
    return os.environ.get("RERANK_MODE", "bedrock").strip().lower()


def _warn(message: str, error: BaseException) -> None:
    print(
        json.dumps(
            {
                "level": "warning",
                "message": message,
                "error": repr(error),
            }
        ),
        flush=True,
    )


def _post_local_rerank(url: str, query: str, texts: list[str]) -> list[dict[str, Any]]:
    import urllib.request

    payload = json.dumps(
        {
            "query": query,
            "texts": texts,
            "raw_scores": False,
            "return_text": False,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=LOCAL_RERANK_TIMEOUT) as response:
        body = json.loads(response.read())

    results = body.get("results") if isinstance(body, dict) else body
    if not isinstance(results, list):
        raise RuntimeError("Local reranker returned an unexpected response")
    return results


def _rank(query: str, candidates: list[dict[str, Any]], top_k: int, url: str) -> list[dict[str, Any]]:
    """Score ``(query, candidate)`` pairs with a local TEI cross-encoder.

    Scores are comparable across batches, so large candidate sets are split to
    respect TEI's max batch size and merged into one global ranking.
    """
    batch_size = max(1, LOCAL_RERANK_BATCH_SIZE)
    ranked: list[dict[str, Any]] = []
    for start in range(0, len(candidates), batch_size):
        batch = candidates[start : start + batch_size]
        results = _post_local_rerank(
            url, query, [candidate["content"] for candidate in batch]
        )
        for result in results:
            index = int(result["index"])
            candidate = dict(batch[index])
            score = result.get("relevance_score", result.get("score", 0.0))
            candidate["rerankScore"] = float(score)
            ranked.append(candidate)

    ranked.sort(key=lambda item: item["rerankScore"], reverse=True)
    return ranked[:top_k]


def _rerank_bedrock(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int,
    model_arn: str,
    region: str,
) -> list[dict[str, Any]]:
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "bedrock-agent-runtime",
        region_name=region,
        config=Config(retries={"max_attempts": 5, "mode": "adaptive"}),
    )
    sources = [
        {
            # The API's enum for an inline document is `INLINE`. `INLINE_DOCUMENT`
            # reads as the obvious name and is what this used to send — the call then
            # failed validation, the `except` below returned the input order, and
            # reranking was silently **never applied** in either caller. Pinned by
            # `tests/test_rerank.py::BedrockRequestShapeTests`.
            "type": "INLINE",
            "inlineDocumentSource": {
                "type": "TEXT",
                "textDocument": {"text": candidate["content"]},
            },
        }
        for candidate in candidates
    ]
    response = client.rerank(
        queries=[{"type": "TEXT", "textQuery": {"text": query}}],
        sources=sources,
        rerankingConfiguration={
            "type": "BEDROCK_RERANKING_MODEL",
            "bedrockRerankingConfiguration": {
                "modelConfiguration": {"modelArn": model_arn},
                "numberOfResults": max(1, min(top_k, len(sources))),
            },
        },
    )

    ranked: list[dict[str, Any]] = []
    for result in response.get("results", []):
        index = int(result["index"])
        candidate = dict(candidates[index])
        candidate["rerankScore"] = float(result.get("relevanceScore", 0.0))
        ranked.append(candidate)
    return ranked[:top_k]


def rerank_candidates(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int,
    *,
    model_arn: str | None = None,
    region: str | None = None,
    url: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Rerank candidates with Bedrock (default) or a local TEI cross-encoder.

    Returns ``(ranked, applied)``. ``applied`` is ``False`` when reranking is
    disabled or the reranker is unreachable, in which case the input order is
    preserved so a search never fails because of the reranker.
    """
    mode = rerank_mode()
    if not candidates or mode == "none":
        return candidates[:top_k], False

    if mode == "local":
        try:
            return (
                _rank(
                    query,
                    candidates,
                    top_k,
                    url or DEFAULT_LOCAL_RERANK_URL,
                ),
                True,
            )
        except Exception as exc:  # noqa: BLE001 - never fail a search on rerank
            _warn("local reranker unavailable; using RRF order", exc)
            return candidates[:top_k], False

    try:
        return (
            _rerank_bedrock(
                query,
                candidates,
                top_k,
                model_arn or DEFAULT_RERANK_MODEL_ARN,
                region or DEFAULT_RERANK_REGION,
            ),
            True,
        )
    except Exception as exc:  # noqa: BLE001 - never fail a search on rerank
        _warn("Bedrock reranker unavailable; using RRF order", exc)
        return candidates[:top_k], False
