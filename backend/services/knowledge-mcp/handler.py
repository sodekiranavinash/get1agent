"""Knowledge MCP server.

Owns the two knowledge tools and does retrieval in-process: it resolves the
caller's knowledge bases from DynamoDB, embeds the query, runs hybrid search
(S3 Vectors + S3 term index) and optionally reranks. There is no separate
retrieval Lambda any more.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from awslabs.mcp_lambda_handler import MCPLambdaHandler

from core.mcp_server import build_handler, require_sub

from retrieval.embedding.config import load_config
from retrieval.embedding.embeddings import embed_texts
from core.json_utils import dumps as json_dumps
from src.search.errors import RetrievalError
from src.search.rerank import rerank_candidates, rerank_mode
from src.search.service import (
    cap_per_document,
    group_sources,
    list_knowledge_bases,
    search,
)
from data.repositories.users import get_user_by_sub

mcp = MCPLambdaHandler(name="get1agent-knowledge", version="1.0.0")

GET_TOOL = "get-user-knowledge-bases"
SEARCH_TOOL = "search-user-knowledge-bases"

DEFAULT_TOP_K = 8
MAX_TOP_K = 50
DEFAULT_MAX_PER_DOCUMENT = 3
DEFAULT_RERANK_CANDIDATES = 30
MAX_CANDIDATE_LIMIT = 100

_GET_SCHEMA: dict[str, Any] = {
    "name": GET_TOOL,
    "description": (
        "Call this FIRST to list the user's ready knowledge bases with their "
        "tags (and tag descriptions), so you know which knowledge base names and "
        "tags exist before searching. Returns a compact list only; use "
        "search-user-knowledge-bases for document content. Do not call this "
        "again during the same task unless the user changes the knowledge bases."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "knowledgeBaseNames": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Knowledge base names to fetch. Omit to list all ready "
                    "knowledge bases."
                ),
            },
        },
    },
}

_SEARCH_SCHEMA: dict[str, Any] = {
    "name": SEARCH_TOOL,
    "description": (
        "Hybrid (semantic + keyword) search across the user's knowledge bases. "
        "Call get-user-knowledge-bases once first to discover the available "
        "knowledge base names and tags. Then call this with ONE well-formed "
        "natural-language query per distinct question — never repeat "
        "near-duplicate searches, and combine related questions into a single "
        "query. Returns the most relevant context with its sources. Each "
        "result's `content` is the full page/section the match came from (use "
        "this to answer) and `matchedContent` is the precise passage that "
        "matched. Set `rerank: true` for higher precision when a query is broad "
        "or ambiguous. Always use this to ground answers in the user's documents."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "One natural-language search query.",
            },
            "knowledgeBaseNames": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Knowledge base names to search. Omit to search all.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Document tag names to filter by. A document matches if it "
                    "has any of the given tags."
                ),
            },
            "rerank": {
                "type": "boolean",
                "description": (
                    "Rerank the results for higher precision. Defaults to false."
                ),
            },
        },
        "required": ["query"],
    },
}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


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


def get_user_knowledge_bases(
    knowledgeBaseNames: list[str] | None = None,
) -> str:
    """Return the user's ready knowledge bases with their tags."""
    try:
        result = list_knowledge_bases(require_sub(), _as_list(knowledgeBaseNames))
    except RetrievalError as exc:
        result = {"knowledgeBases": [], "notFound": [], "error": {"code": exc.code, "message": exc.message}}
    return json_dumps(result)


def search_user_knowledge_bases(
    query: str,
    knowledgeBaseNames: list[str] | None = None,
    tags: list[str] | None = None,
    rerank: bool = False,
) -> str:
    """Run hybrid search across the user's knowledge bases."""
    sub = require_sub()
    try:
        result = _search_cached(
            sub,
            str(query or "").strip(),
            knowledge_base_names=_as_list(knowledgeBaseNames),
            tags=_as_list(tags),
            rerank=bool(rerank),
        )
    except RetrievalError as exc:
        result = {
            "chunks": [],
            "sources": [],
            "meta": {},
            "error": {"code": exc.code, "message": exc.message},
        }
    return json_dumps(result)


def _search_cached(
    sub: str,
    query: str,
    *,
    knowledge_base_names: list[str],
    tags: list[str],
    rerank: bool,
    top_k: int = DEFAULT_TOP_K,
    max_per_document: int = DEFAULT_MAX_PER_DOCUMENT,
) -> dict[str, Any]:
    """Single-flight wrapper around the real ``_search`` (dedupe concurrent work).

    Rate limiting is handled at the API Gateway; this only avoids recomputing the
    same search for concurrent identical requests.
    """
    try:
        from core import cache
    except Exception:  # noqa: BLE001
        cache = None  # type: ignore[assignment]
    try:
        from core import singleflight
    except Exception:  # noqa: BLE001 - dedupe is optional
        singleflight = None  # type: ignore[assignment]

    result_key = ""
    if cache is not None and cache.enabled():
        result_key = cache.cache_key(
            "search",
            sub,
            query,
            ",".join(sorted(knowledge_base_names)),
            ",".join(sorted(tags)),
            bool(rerank),
            top_k,
            max_per_document,
        )
        hit = cache.get(result_key)
        if hit is not None:
            return hit

    def compute() -> dict[str, Any]:
        return _search(
            sub,
            query,
            knowledge_base_names=knowledge_base_names,
            tags=tags,
            rerank=rerank,
            top_k=top_k,
            max_per_document=max_per_document,
        )

    if singleflight is not None and singleflight.enabled() and result_key:
        return singleflight.single_flight(
            lock_key=cache.cache_key("sf", result_key),  # noqa: SLF001
            result_key=result_key,
            ttl_seconds=singleflight.lock_ttl(),
            wait=singleflight.wait_seconds(),
            compute=compute,
        )
    return compute()


def _search(
    sub: str,
    query: str,
    *,
    knowledge_base_names: list[str],
    tags: list[str],
    rerank: bool,
    top_k: int = DEFAULT_TOP_K,
    max_per_document: int = DEFAULT_MAX_PER_DOCUMENT,
) -> dict[str, Any]:
    if not query:
        raise RetrievalError("invalid_request", "query is required")

    try:
        from core import cache
    except Exception:  # noqa: BLE001 - cache is optional
        cache = None  # type: ignore[assignment]
    cache_key = ""
    if cache is not None and cache.enabled():
        cache_key = cache.cache_key(
            "search",
            sub,
            query,
            ",".join(sorted(knowledge_base_names)),
            ",".join(sorted(tags)),
            bool(rerank),
            top_k,
            max_per_document,
        )
        hit = cache.get(cache_key)
        if hit is not None:
            return hit

    try:
        from core import semantic_cache
    except Exception:  # noqa: BLE001 - semantic cache is optional
        semantic_cache = None  # type: ignore[assignment]
    kb_signature = ",".join(sorted(knowledge_base_names)) or "*"

    use_rerank = bool(rerank)
    candidate_limit = _int(
        None,
        DEFAULT_RERANK_CANDIDATES if use_rerank else max(top_k, 10),
        1,
        MAX_CANDIDATE_LIMIT,
    )

    embed_started = time.perf_counter()
    vectors = embed_texts([query], load_config(), input_type="query")
    if not vectors:
        raise RetrievalError("embedding_failed", "Could not embed the query", 502)
    embed_ms = int((time.perf_counter() - embed_started) * 1000)

    if semantic_cache is not None and semantic_cache.enabled():
        semantic_hit = semantic_cache.lookup(
            user_id=sub, vector=vectors[0], require={"kb": kb_signature}
        )
        if semantic_hit is not None:
            return semantic_hit

    search_started = time.perf_counter()
    result = search(
        sub,
        query,
        vectors[0],
        knowledge_base_names=knowledge_base_names,
        tags=tags,
        tag_match="any",
        limit=candidate_limit,
    )
    search_ms = int((time.perf_counter() - search_started) * 1000)

    candidates = result.get("candidates") or []
    warnings = list(result.get("warnings") or [])

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

    payload = {
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
            "searchMs": search_ms,
            "rerankMs": rerank_ms,
        },
        "error": None,
    }
    if cache_key:
        cache.set(cache_key, payload, cache.ttl("search", 300))
    if semantic_cache is not None and semantic_cache.enabled():
        semantic_cache.store(
            user_id=sub,
            vector=vectors[0],
            value=payload,
            vector_id=hashlib.sha256(query.encode("utf-8")).hexdigest()[:32],
            require={"kb": kb_signature},
        )
    return payload


# Register tools explicitly so optional arguments are not marked required.
mcp.tools[GET_TOOL] = _GET_SCHEMA
mcp.tool_implementations[GET_TOOL] = get_user_knowledge_bases
mcp.tools[SEARCH_TOOL] = _SEARCH_SCHEMA
mcp.tool_implementations[SEARCH_TOOL] = search_user_knowledge_bases

def _resolve_user_id(sub: str) -> str | None:
    """Map the HTTP caller's Auth0 sub to the internal userId for retrieval."""
    try:
        profile = get_user_by_sub(sub)
    except Exception:  # noqa: BLE001 - fall through to an unauthenticated tool error
        return None
    return str(profile["userId"]) if profile else None


lambda_handler = build_handler(mcp, resolve_user_id=_resolve_user_id)
