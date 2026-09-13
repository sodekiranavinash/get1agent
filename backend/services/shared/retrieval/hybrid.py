from __future__ import annotations

import os
import re
import uuid
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

# Reciprocal Rank Fusion dampening constant. 60 is the value from the original
# RRF paper and is robust across corpora.
RRF_K = int(os.environ.get("RETRIEVAL_RRF_K", "60"))
# Candidates fetched per leg before fusion.
DEFAULT_CANDIDATE_LIMIT = int(os.environ.get("RETRIEVAL_CANDIDATE_LIMIT", "50"))
# HNSW recall knob; higher = better recall, slower.
HNSW_EF_SEARCH = int(os.environ.get("RETRIEVAL_HNSW_EF_SEARCH", "100"))
SNIPPET_MAX_CHARS = int(os.environ.get("RETRIEVAL_SNIPPET_MAX_CHARS", "600"))

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
# Short English stopword list. The corpus may be multilingual, so we only strip
# obvious filler rather than relying on a language-specific text-search config.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "could",
        "did", "do", "does", "for", "from", "had", "has", "have", "he", "her",
        "here", "his", "how", "i", "if", "in", "into", "is", "it", "its", "me",
        "my", "no", "not", "of", "on", "or", "our", "should", "so", "than",
        "that", "the", "their", "them", "then", "there", "these", "they",
        "this", "to", "too", "up", "us", "was", "we", "were", "what", "when",
        "where", "which", "who", "why", "will", "with", "would", "you", "your",
    }
)


def lexical_tsquery(query: str) -> str:
    """Build an OR/prefix ``tsquery`` so natural-language questions match.

    ``websearch_to_tsquery`` ANDs every term, so a question like "what is the
    personal project in the resume" only matches documents containing *all* of
    those words (including "resume"), which effectively disables the lexical
    leg. Instead we OR the meaningful terms and prefix-match them
    (``project:*``) so plurals/inflections match without language-specific
    stemming.
    """
    tokens = _TOKEN_RE.findall(query.lower())
    terms: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if len(token) < 2 or token in _STOPWORDS or token in seen:
            continue
        seen.add(token)
        terms.append(token)
    if not terms:
        terms = tokens[:8]
    return " | ".join(f"{term}:*" for term in terms)

_VECTOR_LEG = """
SELECT c.id AS chunk_id,
       1 - (c.embedding <=> CAST(:query_vector AS vector)) AS score
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE c.user_id = :user_id
  AND c.knowledge_base_id IN :kb_ids
  AND d.status = 'ready'
  AND c.embedding IS NOT NULL
  {tag_filter}
ORDER BY c.embedding <=> CAST(:query_vector AS vector)
LIMIT :limit
"""

_LEXICAL_LEG = """
WITH q AS (SELECT to_tsquery('simple', :tsquery) AS tsq)
SELECT c.id AS chunk_id,
       ts_rank_cd(c.content_tsv, q.tsq) AS score
FROM chunks c
JOIN documents d ON d.id = c.document_id
CROSS JOIN q
WHERE c.user_id = :user_id
  AND c.knowledge_base_id IN :kb_ids
  AND d.status = 'ready'
  AND c.content_tsv @@ q.tsq
  {tag_filter}
ORDER BY score DESC
LIMIT :limit
"""

_TAG_ANY = """
  AND EXISTS (
      SELECT 1 FROM document_tags dt
      WHERE dt.document_id = c.document_id
        AND lower(dt.name) IN :tags
  )
"""

_TAG_ALL = """
  AND (
      SELECT count(DISTINCT lower(dt.name)) FROM document_tags dt
      WHERE dt.document_id = c.document_id
        AND lower(dt.name) IN :tags
  ) = :tag_count
"""

_FETCH = """
SELECT c.id AS chunk_id, c.document_id, c.knowledge_base_id, c.ordinal,
       c.content, c.page, c.page_end, c.parent_id,
       p.content AS parent_content,
       p.page AS parent_page, p.page_end AS parent_page_end,
       d.file_name, d.content_type,
       kb.name AS kb_name,
       ts_headline(
           'simple', c.content, to_tsquery('simple', :tsquery),
           'StartSel=[[,StopSel=]],MaxWords=60,MinWords=20'
       ) AS snippet
FROM chunks c
JOIN documents d ON d.id = c.document_id
JOIN knowledge_bases kb ON kb.id = c.knowledge_base_id
LEFT JOIN document_parents p ON p.id = c.parent_id
WHERE c.id IN :chunk_ids
"""


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(repr(float(value)) for value in values) + "]"


def _normalize_tags(tags: list[str] | None) -> list[str]:
    return sorted({str(tag).strip().lower() for tag in (tags or []) if str(tag).strip()})


def _tag_clause(tags: list[str], tag_match: str) -> tuple[str, dict[str, Any]]:
    if not tags:
        return "", {}
    if tag_match == "all":
        return _TAG_ALL, {"tag_count": len(tags)}
    return _TAG_ANY, {}


def _clean_snippet(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.replace("[[", "").replace("]]", "").strip()
    if len(cleaned) > SNIPPET_MAX_CHARS:
        cleaned = cleaned[:SNIPPET_MAX_CHARS].rstrip() + "…"
    return cleaned


async def _run_leg(
    session: AsyncSession,
    template: str,
    tag_clause: str,
    params: dict[str, Any],
    tags: list[str],
):
    statement = text(template.format(tag_filter=tag_clause)).bindparams(
        bindparam("kb_ids", expanding=True)
    )
    if tags:
        statement = statement.bindparams(bindparam("tags", expanding=True))
    return (await session.execute(statement, params)).mappings().all()


async def search_candidates(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    kb_ids: list[uuid.UUID],
    query: str,
    query_vector: list[float],
    tags: list[str] | None = None,
    tag_match: str = "any",
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> list[dict[str, Any]]:
    """Hybrid (vector + full-text) retrieval fused with Reciprocal Rank Fusion.

    Runs both legs, fuses by chunk id, then hydrates the best candidates with
    document/knowledge-base metadata and a highlighted snippet.
    """
    if not kb_ids or not query.strip():
        return []

    normalized_tags = _normalize_tags(tags)
    tag_clause, tag_params = _tag_clause(normalized_tags, tag_match)
    common: dict[str, Any] = {
        "user_id": user_id,
        "kb_ids": kb_ids,
        "limit": limit,
        **tag_params,
    }
    if tag_clause:
        common["tags"] = normalized_tags

    await session.execute(
        text("SELECT set_config('hnsw.ef_search', :value, true)"),
        {"value": str(HNSW_EF_SEARCH)},
    )

    tsquery = lexical_tsquery(query)

    vector_rows = await _run_leg(
        session,
        _VECTOR_LEG,
        tag_clause,
        {**common, "query_vector": _vector_literal(query_vector)},
        normalized_tags,
    )
    lexical_rows = await _run_leg(
        session,
        _LEXICAL_LEG,
        tag_clause,
        {**common, "tsquery": tsquery},
        normalized_tags,
    )

    fused: dict[int, dict[str, Any]] = {}
    for rank, row in enumerate(vector_rows, start=1):
        entry = fused.setdefault(row["chunk_id"], {"chunkId": row["chunk_id"]})
        entry["vectorScore"] = float(row["score"])
        entry["rrfScore"] = entry.get("rrfScore", 0.0) + 1.0 / (RRF_K + rank)
    for rank, row in enumerate(lexical_rows, start=1):
        entry = fused.setdefault(row["chunk_id"], {"chunkId": row["chunk_id"]})
        entry["lexicalScore"] = float(row["score"])
        entry["rrfScore"] = entry.get("rrfScore", 0.0) + 1.0 / (RRF_K + rank)

    if not fused:
        return []

    ordered = sorted(
        fused.values(), key=lambda item: item["rrfScore"], reverse=True
    )[:limit]
    chunk_ids = [entry["chunkId"] for entry in ordered]

    detail_rows = (
        await session.execute(
            text(_FETCH).bindparams(bindparam("chunk_ids", expanding=True)),
            {"tsquery": tsquery, "chunk_ids": chunk_ids},
        )
    ).mappings().all()
    details = {row["chunk_id"]: row for row in detail_rows}

    candidates: list[dict[str, Any]] = []
    seen_parents: set[int] = set()
    for entry in ordered:
        row = details.get(entry["chunkId"])
        if row is None:
            continue
        # Small-to-big: several matched children can belong to one parent
        # (page/section). Return each parent once, using its full text as the
        # context and the matched child as the precise citation.
        parent_id = row["parent_id"]
        if parent_id is not None:
            if parent_id in seen_parents:
                continue
            seen_parents.add(parent_id)
        parent_page = (
            row["parent_page"] if row["parent_page"] is not None else row["page"]
        )
        parent_page_end = (
            row["parent_page_end"]
            if row["parent_page_end"] is not None
            else row["page_end"]
        )
        candidates.append(
            {
                "chunkId": row["chunk_id"],
                "documentId": str(row["document_id"]),
                "knowledgeBaseId": str(row["knowledge_base_id"]),
                "kbName": row["kb_name"],
                "fileName": row["file_name"],
                "contentType": row["content_type"],
                "page": parent_page,
                "pageEnd": parent_page_end,
                "ordinal": row["ordinal"],
                "parentId": parent_id,
                "content": row["parent_content"] or row["content"],
                "matchedContent": row["content"],
                "snippet": _clean_snippet(row["snippet"]),
                "vectorScore": entry.get("vectorScore"),
                "lexicalScore": entry.get("lexicalScore"),
                "rrfScore": entry["rrfScore"],
            }
        )
    return candidates
