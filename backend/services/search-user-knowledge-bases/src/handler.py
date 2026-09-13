from __future__ import annotations

import json
import os
import sys
import time
import traceback
from typing import Any

from shared.ingestion.config import load_config
from shared.ingestion.embeddings import embed_texts
from shared.retrieval import (
    RetrievalError,
    cap_per_document,
    group_sources,
    rerank_candidates,
    rerank_mode,
)

DEFAULT_TOP_K = 8
MAX_TOP_K = 50
DEFAULT_MAX_PER_DOCUMENT = 3
DEFAULT_RERANK_CANDIDATES = 30
MAX_CANDIDATE_LIMIT = 100


def _int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _invoke_retrieval(payload: dict[str, Any]) -> dict[str, Any]:
    function_name = os.environ.get("RETRIEVAL_QUERY_FUNCTION")
    if not function_name:
        raise RuntimeError("RETRIEVAL_QUERY_FUNCTION is not set")

    import boto3

    client = boto3.client("lambda", region_name=os.environ.get("AWS_REGION"))
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    raw = response["Payload"].read()
    if response.get("FunctionError"):
        detail = raw[:500].decode("utf-8", "replace")
        raise RuntimeError(f"retrieval-query failed: {detail}")
    try:
        return json.loads(raw or b"{}")
    except ValueError as exc:
        raise RuntimeError("retrieval-query returned invalid JSON") from exc


def _search(payload: dict[str, Any]) -> dict[str, Any]:
    sub = str(payload.get("auth0Sub") or payload.get("sub") or "").strip()
    if not sub:
        raise RetrievalError("unauthorized", "auth0Sub is required", 401)
    query = str(payload.get("query") or "").strip()
    if not query:
        raise RetrievalError("invalid_request", "query is required")

    top_k = _int(payload.get("topK"), DEFAULT_TOP_K, 1, MAX_TOP_K)
    max_per_document = _int(
        payload.get("maxChunksPerDocument"), DEFAULT_MAX_PER_DOCUMENT, 0, 20
    )
    use_rerank = _bool(payload.get("rerank"), False)
    candidate_limit = _int(
        payload.get("candidateLimit"),
        DEFAULT_RERANK_CANDIDATES if use_rerank else max(top_k, 10),
        1,
        MAX_CANDIDATE_LIMIT,
    )

    warnings: list[str] = []
    if _bool(payload.get("includeImages"), False):
        warnings.append(
            "Image retrieval is not enabled; only text chunks were searched."
        )

    embed_started = time.perf_counter()
    vectors = embed_texts([query], load_config())
    if not vectors:
        raise RetrievalError("embedding_failed", "Could not embed the query", 502)
    embed_ms = int((time.perf_counter() - embed_started) * 1000)

    sql_started = time.perf_counter()
    result = _invoke_retrieval(
        {
            "auth0Sub": sub,
            "query": query,
            "queryVector": vectors[0],
            "knowledgeBaseNames": payload.get("knowledgeBaseNames") or [],
            "knowledgeBaseIds": payload.get("knowledgeBaseIds") or [],
            "tags": payload.get("tags") or [],
            "tagMatch": payload.get("tagMatch") or "any",
            "limit": candidate_limit,
        }
    )
    sql_ms = int((time.perf_counter() - sql_started) * 1000)

    if isinstance(result.get("error"), dict):
        error = result["error"]
        raise RetrievalError(
            str(error.get("code") or "retrieval_failed"),
            str(error.get("message") or "Retrieval failed"),
        )

    candidates = result.get("candidates") or []
    warnings.extend(result.get("warnings") or [])

    rerank_started = time.perf_counter()
    if use_rerank and candidates:
        ranked, reranked = rerank_candidates(
            query,
            candidates,
            min(len(candidates), max(top_k, DEFAULT_RERANK_CANDIDATES)),
        )
        if not reranked:
            warnings.append(
                "Reranking was requested but not applied; results use RRF order."
            )
    else:
        ranked, reranked = candidates, False
    selected = cap_per_document(ranked, max_per_document)[:top_k]
    rerank_ms = int((time.perf_counter() - rerank_started) * 1000)

    chunks = [
        {
            "chunkId": candidate["chunkId"],
            "documentId": candidate["documentId"],
            "knowledgeBaseId": candidate["knowledgeBaseId"],
            "kbName": candidate["kbName"],
            "fileName": candidate["fileName"],
            "page": candidate["page"],
            "pageEnd": candidate["pageEnd"],
            # ``content`` is the parent (page/section) returned for context;
            # ``matchedContent`` is the precise child that matched the query.
            "content": candidate["content"],
            "matchedContent": candidate.get("matchedContent"),
            "vectorScore": candidate.get("vectorScore"),
            "lexicalScore": candidate.get("lexicalScore"),
            "rrfScore": candidate.get("rrfScore"),
            "rerankScore": candidate.get("rerankScore"),
        }
        for candidate in selected
    ]

    return {
        "chunks": chunks,
        "sources": group_sources(selected),
        "meta": {
            "noResults": not chunks,
            "reranked": reranked,
            "rerankMode": rerank_mode(),
            "candidateCount": len(candidates),
            "returned": len(chunks),
            "knowledgeBases": result.get("knowledgeBases") or [],
            "notFound": result.get("notFound") or [],
            "warnings": warnings,
            "embedMs": embed_ms,
            "sqlMs": sql_ms,
            "rerankMs": rerank_ms,
        },
        "error": None,
    }


def _log_search(payload: dict[str, Any], result: dict[str, Any]) -> None:
    meta = result.get("meta") or {}
    print(
        json.dumps(
            {
                "level": "info",
                "message": "retrieval search",
                "auth0Sub": payload.get("auth0Sub") or payload.get("sub"),
                "knowledgeBaseNames": payload.get("knowledgeBaseNames"),
                "tags": payload.get("tags"),
                "rerank": bool(payload.get("rerank")),
                "candidateCount": meta.get("candidateCount"),
                "returned": meta.get("returned"),
                "embedMs": meta.get("embedMs"),
                "sqlMs": meta.get("sqlMs"),
                "rerankMs": meta.get("rerankMs"),
            },
            default=str,
        ),
        flush=True,
    )


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    payload = event if isinstance(event, dict) else {}
    try:
        result = _search(payload)
    except RetrievalError as exc:
        return {
            "chunks": [],
            "sources": [],
            "meta": {},
            "error": {"code": exc.code, "message": exc.message},
        }
    except Exception as exc:  # noqa: BLE001
        print(f"search-user-knowledge-bases error: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        return {
            "chunks": [],
            "sources": [],
            "meta": {},
            "error": {"code": "internal_error", "message": "Search failed"},
        }
    _log_search(payload, result)
    return result
