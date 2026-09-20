from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_RERANK_REGION = os.environ.get("RERANK_REGION", "us-west-2")
DEFAULT_RERANK_MODEL_ARN = os.environ.get(
    "RERANK_MODEL_ARN",
    "arn:aws:bedrock:us-west-2::foundation-model/amazon.rerank-v1:0",
)
# Voyage AI reranker (https://docs.voyageai.com/reference/reranker-api).
DEFAULT_VOYAGE_RERANK_MODEL = os.environ.get(
    "VOYAGE_RERANK_MODEL", "rerank-3"
)
DEFAULT_VOYAGE_API_BASE_URL = os.environ.get(
    "VOYAGE_API_BASE_URL", "https://api.voyageai.com/v1"
)
VOYAGE_RERANK_TIMEOUT = int(
    os.environ.get("VOYAGE_RERANK_TIMEOUT_SECONDS", "60")
)
# Local cross-encoder served by HuggingFace Text Embeddings Inference (TEI).
DEFAULT_LOCAL_RERANK_URL = os.environ.get(
    "LOCAL_RERANK_URL", "http://reranker:80/rerank"
)
LOCAL_RERANK_TIMEOUT = int(os.environ.get("LOCAL_RERANK_TIMEOUT_SECONDS", "60"))
# TEI rejects requests above the model's max batch (32 for MiniLM-L6); split.
LOCAL_RERANK_BATCH_SIZE = int(os.environ.get("LOCAL_RERANK_BATCH_SIZE", "32"))


def rerank_mode() -> str:
    """``voyage`` (default), ``bedrock``, ``local`` (TEI) or ``none``."""
    return os.environ.get("RERANK_MODE", "voyage").strip().lower()


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

    client = boto3.client("bedrock-agent-runtime", region_name=region)
    sources = [
        {
            "type": "INLINE_DOCUMENT",
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


def _rerank_voyage(
    query: str, candidates: list[dict[str, Any]], top_k: int
) -> list[dict[str, Any]]:
    """Score ``(query, candidate)`` pairs with the Voyage rerank API."""
    import urllib.error
    import urllib.request

    api_key = os.environ.get("VOYAGE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY is not configured")

    payload = json.dumps(
        {
            "query": query,
            "documents": [candidate["content"] for candidate in candidates],
            "model": DEFAULT_VOYAGE_RERANK_MODEL,
            "top_k": max(1, min(top_k, len(candidates))),
            "truncation": True,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{DEFAULT_VOYAGE_API_BASE_URL.rstrip('/')}/rerank",
        data=payload,
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=VOYAGE_RERANK_TIMEOUT
        ) as response:
            body = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:500].decode("utf-8", "replace")
        raise RuntimeError(f"Voyage rerank returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach Voyage rerank: {exc.reason}") from exc

    ranked: list[dict[str, Any]] = []
    for result in body.get("data") or []:
        index = int(result["index"])
        candidate = dict(candidates[index])
        candidate["rerankScore"] = float(result.get("relevance_score", 0.0))
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
    """Rerank candidates with Voyage (default), Bedrock or a local TEI cross-encoder.

    Returns ``(ranked, applied)``. ``applied`` is ``False`` when reranking is
    disabled or the reranker is unreachable, in which case the input order is
    preserved so a search never fails because of the reranker.
    """
    mode = rerank_mode()
    if not candidates or mode == "none":
        return candidates[:top_k], False

    if mode == "voyage":
        try:
            return _rerank_voyage(query, candidates, top_k), True
        except Exception as exc:  # noqa: BLE001 - never fail a search on rerank
            _warn("Voyage reranker unavailable; using RRF order", exc)
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
