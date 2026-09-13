from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shared.models import Document, KnowledgeBase
from shared.retrieval.errors import RetrievalError
from shared.retrieval.hybrid import DEFAULT_CANDIDATE_LIMIT, search_candidates
from shared.retrieval.resolver import resolve_knowledge_bases
from shared.users import get_user_by_sub

MAX_CANDIDATE_LIMIT = 200
VALID_TAG_MATCH = ("any", "all")


def auth_sub(payload: dict[str, Any]) -> str:
    value = payload.get("auth0Sub") or payload.get("sub")
    sub = str(value or "").strip()
    if not sub:
        raise RetrievalError("unauthorized", "auth0Sub is required", 401)
    return sub


def _serialize_knowledge_base(kb: KnowledgeBase) -> dict[str, Any]:
    """Shape a knowledge base for the discovery tool.

    Kept intentionally small: the model only needs the name (the identifier it
    passes back to ``search-user-knowledge-bases``), a description, and the
    tags it can filter on. Documents, ids, counts and embedding/config metadata
    are omitted to keep the context lean.
    """
    tag_index: dict[str, dict[str, Any]] = {}
    for document in kb.documents:
        for tag in document.tags:
            tag_index.setdefault(
                tag.name.lower(),
                {"name": tag.name, "description": tag.description or ""},
            )

    return {
        "name": kb.name,
        "description": kb.description,
        "tags": sorted(tag_index.values(), key=lambda item: item["name"].lower()),
    }


async def list_knowledge_bases(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Backing query for the ``get-user-knowledge-bases`` tool."""
    user = await get_user_by_sub(session, auth_sub(payload))
    if user is None:
        raise RetrievalError("user_not_found", "No account found for this user", 404)

    matched, not_found = await resolve_knowledge_bases(
        session,
        user.id,
        payload.get("knowledgeBaseNames"),
    )

    if matched:
        ids = [kb.id for kb in matched]
        matched = list(
            (
                await session.execute(
                    select(KnowledgeBase)
                    .options(
                        selectinload(KnowledgeBase.documents).selectinload(
                            Document.tags
                        )
                    )
                    .where(KnowledgeBase.id.in_(ids))
                    .order_by(KnowledgeBase.name)
                )
            )
            .scalars()
            .all()
        )

    # Only ready knowledge bases are searchable, so only those are discoverable.
    matched = [kb for kb in matched if kb.status == "ready"]

    return {
        "knowledgeBases": [_serialize_knowledge_base(kb) for kb in matched],
        "notFound": not_found,
    }


def _validated_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CANDIDATE_LIMIT
    return max(1, min(MAX_CANDIDATE_LIMIT, limit))


async def execute_retrieval_query(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Backing query for the ``search-user-knowledge-bases`` tool.

    Resolves the caller + knowledge bases, runs hybrid search, and returns
    ranked candidate chunks plus any warnings. The caller (outside the VPC)
    owns embedding and reranking; this function owns all database access.
    """
    user = await get_user_by_sub(session, auth_sub(payload))
    if user is None:
        raise RetrievalError("user_not_found", "No account found for this user", 404)

    query = str(payload.get("query") or "").strip()
    if not query:
        raise RetrievalError("invalid_request", "query is required")

    query_vector = payload.get("queryVector")
    if not isinstance(query_vector, list) or not query_vector:
        raise RetrievalError("invalid_request", "queryVector is required")

    tag_match = str(payload.get("tagMatch") or "any").strip().lower()
    if tag_match not in VALID_TAG_MATCH:
        raise RetrievalError(
            "invalid_request", f"tagMatch must be one of {list(VALID_TAG_MATCH)}"
        )

    tags = payload.get("tags") if isinstance(payload.get("tags"), list) else []
    limit = _validated_limit(payload.get("limit"))

    matched, not_found = await resolve_knowledge_bases(
        session,
        user.id,
        payload.get("knowledgeBaseNames"),
        payload.get("knowledgeBaseIds"),
    )

    warnings: list[str] = []
    if not_found:
        warnings.append(f"Unknown knowledge bases: {', '.join(not_found)}")

    dimension = len(query_vector)
    eligible: list[KnowledgeBase] = []
    for kb in matched:
        if kb.status != "ready":
            warnings.append(f'Knowledge base "{kb.name}" is {kb.status}; skipped')
            continue
        if kb.embedding_dim != dimension:
            warnings.append(
                f'Knowledge base "{kb.name}" uses {kb.embedding_dim}-dim vectors; skipped'
            )
            continue
        eligible.append(kb)

    if not eligible:
        return {
            "candidates": [],
            "knowledgeBases": [],
            "notFound": not_found,
            "warnings": warnings,
        }

    candidates = await search_candidates(
        session,
        user_id=user.id,
        kb_ids=[kb.id for kb in eligible],
        query=query,
        query_vector=[float(value) for value in query_vector],
        tags=[str(tag) for tag in tags],
        tag_match=tag_match,
        limit=limit,
    )

    return {
        "candidates": candidates,
        "knowledgeBases": [
            {"id": str(kb.id), "name": kb.name, "status": kb.status}
            for kb in eligible
        ],
        "notFound": not_found,
        "warnings": warnings,
    }


# --- response shaping --------------------------------------------------------


def cap_per_document(
    candidates: list[dict[str, Any]], max_per_document: int
) -> list[dict[str, Any]]:
    """Keep at most N chunks per document, preserving order."""
    if max_per_document <= 0:
        return candidates
    counts: dict[str, int] = {}
    kept: list[dict[str, Any]] = []
    for candidate in candidates:
        document_id = candidate["documentId"]
        if counts.get(document_id, 0) >= max_per_document:
            continue
        counts[document_id] = counts.get(document_id, 0) + 1
        kept.append(candidate)
    return kept


def source_url(kb_id: str, document_id: str, page: int | None) -> str:
    base = f"/v1/knowledge-bases/{kb_id}/documents/{document_id}/file"
    return f"{base}#page={page}" if page else base


def group_sources(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One source per (document, page); keep the best score and list chunk ids."""
    groups: dict[tuple[str, Any], dict[str, Any]] = {}
    for candidate in candidates:
        key = (candidate["documentId"], candidate["page"])
        score = (
            candidate.get("rerankScore")
            or candidate.get("rrfScore")
            or candidate.get("vectorScore")
            or 0.0
        )
        existing = groups.get(key)
        if existing is None:
            groups[key] = {
                "documentId": candidate["documentId"],
                "knowledgeBaseId": candidate["knowledgeBaseId"],
                "kbName": candidate["kbName"],
                "fileName": candidate["fileName"],
                "contentType": candidate["contentType"],
                "page": candidate["page"],
                "pageEnd": candidate["pageEnd"],
                "snippet": candidate["snippet"],
                "score": score,
                "chunkIds": [candidate["chunkId"]],
                "sourceUrl": source_url(
                    candidate["knowledgeBaseId"],
                    candidate["documentId"],
                    candidate["page"],
                ),
            }
        elif score > existing["score"]:
            existing["score"] = score
            existing["snippet"] = candidate["snippet"]
            existing["chunkIds"].append(candidate["chunkId"])
        else:
            existing["chunkIds"].append(candidate["chunkId"])
    return sorted(groups.values(), key=lambda item: item["score"], reverse=True)
