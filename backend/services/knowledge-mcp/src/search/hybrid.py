"""Hybrid retrieval: S3 Vectors (semantic) + S3 term index (BM25), fused with RRF.

Both legs run in parallel; only the small child chunks are searched. Results are
hydrated from the parent objects (one ``GetObject`` per unique parent) so the
caller gets the parent's full text for context plus the precise matched child.
Round trips are fixed and independent of corpus size.
"""

from __future__ import annotations

import math
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from retrieval.layout import parent_key, query_terms
from retrieval.s3_vectors import VectorMatch, VectorStore
from retrieval.term_index import expand_prefix, read_stats, read_term
from core.storage import Storage

# Reciprocal Rank Fusion dampening constant (from the original RRF paper).
RRF_K = int(os.environ.get("RETRIEVAL_RRF_K", "60"))
DEFAULT_CANDIDATE_LIMIT = int(os.environ.get("RETRIEVAL_CANDIDATE_LIMIT", "50"))
SEMANTIC_TOP_K = int(os.environ.get("RETRIEVAL_SEMANTIC_TOP_K", "100"))
SNIPPET_MAX_CHARS = int(os.environ.get("RETRIEVAL_SNIPPET_MAX_CHARS", "600"))
# BM25 knobs.
BM25_K1 = float(os.environ.get("RETRIEVAL_BM25_K1", "1.2"))
BM25_B = float(os.environ.get("RETRIEVAL_BM25_B", "0.75"))
MAX_EXPANDED_TERMS = int(os.environ.get("RETRIEVAL_MAX_TERMS", "60"))
# Cap on parent-object GETs per search.
MAX_HYDRATED_PARENTS = int(os.environ.get("RETRIEVAL_MAX_PARENTS", "100"))


def _idf(document_count: int, df: int) -> float:
    return math.log(1 + (document_count - df + 0.5) / (df + 0.5))


def _snippet(text: str, terms: list[str], max_chars: int = SNIPPET_MAX_CHARS) -> str:
    if not text:
        return ""
    lowered = text.lower()
    position = -1
    for term in terms:
        found = lowered.find(term)
        if found != -1 and (position == -1 or found < position):
            position = found
    if position == -1:
        snippet = text[:max_chars]
    else:
        start = max(0, position - 200)
        if start > 0:
            space = text.find(" ", start)
            if space != -1 and space < position:
                start = space + 1
        snippet = text[start : start + max_chars]
    snippet = snippet.strip()
    if len(text) > len(snippet) and position + max_chars < len(text):
        snippet = snippet.rstrip() + "…"
    return snippet


def _vector_leg(
    store: VectorStore,
    sub: str,
    query_vector: list[float],
    kb_ids: list[str],
) -> list[VectorMatch]:
    filters: dict[str, Any] = {"status": "ready"}
    if kb_ids:
        filters["kbId"] = kb_ids
    return store.query(sub, query_vector, SEMANTIC_TOP_K, filters=filters)


def _lexical_leg(
    storage: Storage,
    sub: str,
    query: str,
    kb_ids: list[str],
    allowed_doc_ids: set[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    terms = query_terms(query)
    if not terms:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(terms))) as pool:
        expansions = list(pool.map(lambda term: expand_prefix(storage, sub, term), terms))
    expanded: list[str] = []
    seen: set[str] = set()
    for tokens in expansions:
        for token in tokens:
            if token not in seen:
                seen.add(token)
                expanded.append(token)
    expanded = expanded[:MAX_EXPANDED_TERMS]

    stats = read_stats(storage, sub)
    document_count = int(stats.get("chunkCount") or 0)
    avgdl = float(stats.get("avgdl") or 0.0) or 1.0
    kb_filter = set(kb_ids) if kb_ids else None

    with ThreadPoolExecutor(max_workers=min(8, len(expanded) or 1)) as pool:
        term_objects = list(
            pool.map(lambda token: (token, read_term(storage, sub, token)), expanded)
        )

    scores: dict[str, dict[str, Any]] = {}
    for token, data in term_objects:
        if not data:
            continue
        postings = data.get("postings") or []
        df = int(data.get("df") or len(postings))
        if not df:
            continue
        idf = _idf(document_count, df)
        for posting in postings:
            if kb_filter and posting.get("kbId") not in kb_filter:
                continue
            doc_id = str(posting.get("docId") or "")
            if allowed_doc_ids is not None and doc_id not in allowed_doc_ids:
                continue
            chunk_id = str(posting.get("chunkId") or "")
            tf = int(posting.get("tf") or 0)
            dl = int(posting.get("dl") or 0) or 1
            denominator = tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl)
            score = idf * (tf * (BM25_K1 + 1)) / denominator if denominator else 0.0
            entry = scores.setdefault(
                chunk_id,
                {
                    "chunkId": chunk_id,
                    "parentId": posting.get("parentId"),
                    "docId": doc_id,
                    "score": 0.0,
                },
            )
            entry["score"] += score

    ordered = sorted(scores.values(), key=lambda item: item["score"], reverse=True)
    return ordered[:limit]


def _load_parent(storage: Storage, sub: str, parent_id: str) -> dict[str, Any] | None:
    return storage.get_json(parent_key(sub, parent_id))


def search_candidates(
    storage: Storage,
    store: VectorStore,
    sub: str,
    *,
    kb_ids: list[str],
    query: str,
    query_vector: list[float],
    limit: int = DEFAULT_CANDIDATE_LIMIT,
    allowed_doc_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    if not kb_ids or not query.strip():
        return []

    with ThreadPoolExecutor(max_workers=2) as pool:
        semantic_future = pool.submit(_vector_leg, store, sub, query_vector, kb_ids)
        lexical_future = pool.submit(
            _lexical_leg, storage, sub, query, kb_ids, allowed_doc_ids, limit
        )
        semantic = semantic_future.result()
        lexical = lexical_future.result()

    fused: dict[str, dict[str, Any]] = {}
    vector_meta: dict[str, dict[str, Any]] = {}
    for rank, match in enumerate(semantic, start=1):
        # chunkId is ``<docId>#<ord>``; tag filtering is applied post-query
        # because tags are not part of the vector metadata.
        doc_id = match.key.rsplit("#", 1)[0]
        if allowed_doc_ids is not None and doc_id not in allowed_doc_ids:
            continue
        entry = fused.setdefault(match.key, {"chunkId": match.key})
        entry["vectorScore"] = float(match.score)
        entry["rrfScore"] = entry.get("rrfScore", 0.0) + 1.0 / (RRF_K + rank)
        if match.metadata.get("parentId"):
            entry["parentId"] = match.metadata["parentId"]
        vector_meta[match.key] = match.metadata
    for rank, row in enumerate(lexical, start=1):
        entry = fused.setdefault(row["chunkId"], {"chunkId": row["chunkId"]})
        entry["lexicalScore"] = float(row["score"])
        entry["rrfScore"] = entry.get("rrfScore", 0.0) + 1.0 / (RRF_K + rank)
        if row.get("parentId"):
            entry["parentId"] = row["parentId"]

    if not fused:
        return []

    ordered = sorted(fused.values(), key=lambda item: item["rrfScore"], reverse=True)[
        :limit
    ]

    # Hydrate the unique parent objects (one GET per parent, in parallel).
    parent_ids = [
        entry["parentId"]
        for entry in ordered
        if entry.get("parentId")
    ][:MAX_HYDRATED_PARENTS]
    unique_parents = list(dict.fromkeys(parent_ids))
    parents: dict[str, dict[str, Any]] = {}
    if unique_parents:
        with ThreadPoolExecutor(max_workers=min(8, len(unique_parents))) as pool:
            loaded = list(
                pool.map(lambda pid: (pid, _load_parent(storage, sub, pid)), unique_parents)
            )
        parents = {pid: data for pid, data in loaded if data}

    terms = query_terms(query)
    candidates: list[dict[str, Any]] = []
    seen_parents: set[str] = set()
    for entry in ordered:
        parent_id = entry.get("parentId")
        parent = parents.get(parent_id) if parent_id else None
        metadata = vector_meta.get(entry["chunkId"], {})
        if parent is None and not metadata:
            continue
        if parent_id:
            if parent_id in seen_parents:
                continue
            seen_parents.add(parent_id)

        child = None
        if parent:
            for item in parent.get("children") or []:
                if item.get("chunkId") == entry["chunkId"]:
                    child = item
                    break
        matched_content = (
            (child or {}).get("text")
            or metadata.get("text")
            or (parent or {}).get("content")
            or ""
        )
        content = (parent or {}).get("content") or matched_content
        parent_page = (parent or {}).get("page")
        child_page = (child or {}).get("page")
        parent_page_end = (parent or {}).get("pageEnd")
        child_page_end = (child or {}).get("pageEnd")

        candidates.append(
            {
                "chunkId": entry["chunkId"],
                "documentId": (parent or {}).get("docId")
                or metadata.get("docId")
                or entry.get("docId"),
                "knowledgeBaseId": (parent or {}).get("kbId") or metadata.get("kbId"),
                "kbName": (parent or {}).get("kbName") or metadata.get("kbName"),
                "fileName": (parent or {}).get("fileName") or metadata.get("fileName"),
                "contentType": (parent or {}).get("contentType"),
                "page": parent_page if parent_page is not None else child_page,
                "pageEnd": parent_page_end
                if parent_page_end is not None
                else child_page_end,
                "ordinal": (child or {}).get("ordinal"),
                "parentId": parent_id,
                "content": content,
                "matchedContent": matched_content,
                "snippet": _snippet(matched_content, terms),
                "vectorScore": entry.get("vectorScore"),
                "lexicalScore": entry.get("lexicalScore"),
                "rrfScore": entry["rrfScore"],
            }
        )
    return candidates
