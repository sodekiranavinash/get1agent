"""Retrieve platform knowledge for an Avi answer.

Avi's knowledge base is an **ordinary knowledge base** owned by the reserved
``platform`` scope (see ``tools/avi-knowledge/scope.py``), so this module does not
invent a retrieval system: it reuses the platform's own primitives —

* ``retrieval.embedding.embeddings.embed_texts`` for the query vector (which is
  cached, so a repeated question costs no Bedrock call);
* ``retrieval.s3_vectors`` for the semantic leg (``idx-platform``);
* ``retrieval.term_index`` + BM25 for the lexical leg;
* ``retrieval.layout.parent_key`` for small-to-big hydration;
* ``core.cache`` for the exact-match payload cache.

The fusion (Reciprocal Rank Fusion) lives here rather than in the knowledge MCP
because Avi is deliberately a **separate service**: it depends on the shared
packages, never on another service's ``src`` package. The orchestration is ~100
lines and documented, which is a smaller risk than coupling a new runtime to the
live retrieval path.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from core import cache
from core.storage import Storage
from retrieval.embedding.config import load_config
from retrieval.embedding.embeddings import embed_texts
from retrieval.layout import parent_key, query_terms
from retrieval.s3_vectors import VectorMatch, vector_store
from retrieval.term_index import expand_prefix, read_stats, read_term

from avi import settings

# Reciprocal Rank Fusion dampening constant (from the original RRF paper).
RRF_K = int(os.environ.get("AVI_RRF_K", "60") or "60")
SEMANTIC_TOP_K = int(os.environ.get("AVI_SEMANTIC_TOP_K", "60") or "60")
MAX_TERMS = int(os.environ.get("AVI_MAX_TERMS", "40") or "40")
MAX_PARENTS = int(os.environ.get("AVI_MAX_PARENTS", "40") or "40")
DEFAULT_TOP_K = int(os.environ.get("AVI_TOP_K", "6") or "6")
SNIPPET_CHARS = int(os.environ.get("AVI_SNIPPET_CHARS", "600") or "600")
# BM25 knobs — identical to the platform's knowledge search, so relevance ranks
# the same way here as it does in the real product.
BM25_K1 = float(os.environ.get("AVI_BM25_K1", "1.2") or "1.2")
BM25_B = float(os.environ.get("AVI_BM25_B", "0.75") or "0.75")
CACHE_TTL_SECONDS = int(os.environ.get("AVI_RETRIEVAL_CACHE_TTL_SECONDS", "300") or "300")


class RetrievalError(RuntimeError):
    """Retrieval could not run (reported as a warning, never a hard failure)."""


@dataclass
class Passage:
    """One retrieved passage, shaped for prompts and the UI source carousel."""

    index: int
    title: str
    route: str
    content: str
    matched: str
    snippet: str
    score: float
    doc_id: str = ""
    kb_id: str = ""
    page: int | None = None
    source: str = "knowledge"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "title": self.title,
            "route": self.route,
            "content": self.content,
            "matchedContent": self.matched,
            "snippet": self.snippet,
            "score": round(self.score, 6),
            "documentId": self.doc_id,
            "knowledgeBaseId": self.kb_id,
            "page": self.page,
            "kind": self.source,
            "contentType": "text/markdown",
        }

    def to_source(self) -> dict[str, Any]:
        """The ``sources[]`` entry the chat UI already knows how to render."""
        return {
            "kind": "knowledge",
            "index": self.index,
            "title": self.title,
            "subtitle": self.route or "Platform docs",
            "route": self.route,
            "url": self.route,
            "snippet": self.snippet,
            "documentId": self.doc_id,
            "knowledgeBaseId": self.kb_id,
            "page": self.page,
        }



#: Field ordering inside a corpus file's frontmatter.
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _vector_filter(kb_id: str) -> dict[str, Any]:
    """The filter the index actually supports.

    The shared indexer stores ``kbId`` and ``status`` on each vector — there is no
    ``scope`` field — so filtering on anything else matches every row out and the
    semantic leg silently returns nothing.
    """
    filters: dict[str, Any] = {"status": "ready"}
    if kb_id:
        filters["kbId"] = [kb_id]
    return filters


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Read the corpus frontmatter out of a chunk or parent's text.

    Avi's documents carry their page route, title and audience in YAML
    frontmatter, which the shared indexer treats as ordinary text. Parsing it here
    keeps `route` and `title` available for citations and lets the admin-only
    documents stay out of a non-admin answer — without forking the pipeline.
    """
    match = _FRONTMATTER_RE.match(text or "")
    if not match:
        return {}
    fields: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.startswith((" ", "\t", "-")):
            continue
        key, _, raw = line.partition(":")
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[key.strip()] = value
    return fields


def _audience_allowed(audience: str, *, allow_admin: bool) -> bool:
    """Whether a passage may be shown to this caller.

    Only ``admin`` is restricted: public and user documents are visible to
    everyone (an admin sees all three).
    """
    return allow_admin or audience != "admin"


def _idf(document_count: int, df: int) -> float:
    return math.log(1 + (document_count - df + 0.5) / (df + 0.5))


def _snippet(text: str, terms: list[str], limit: int = SNIPPET_CHARS) -> str:
    if not text:
        return ""
    lowered = text.lower()
    position = -1
    for term in terms:
        found = lowered.find(term)
        if found != -1 and (position == -1 or found < position):
            position = found
    if position == -1:
        return text[:limit].strip()
    start = max(0, position - 160)
    if start > 0:
        space = text.find(" ", start)
        if space != -1 and space < position:
            start = space + 1
    snippet = text[start : start + limit].strip()
    if start > 0:
        snippet = "…" + snippet
    if position + limit < len(text):
        snippet = snippet.rstrip() + "…"
    return snippet


def _load_parent(storage: Storage, scope: str, parent_id: str) -> dict[str, Any] | None:
    try:
        data = storage.get_json(parent_key(scope, parent_id))
    except Exception:  # noqa: BLE001 - a missing parent just drops one candidate
        return None
    return data if isinstance(data, dict) else None


def _lexical_leg(
    storage: Storage, scope: str, query: str, limit: int
) -> list[dict[str, Any]]:
    """BM25 over the S3 term index (the lexical half of hybrid search)."""
    terms = query_terms(query)[:MAX_TERMS]
    if not terms:
        return []
    stats = read_stats(storage, scope)
    document_count = int(stats.get("chunkCount") or 0)
    avgdl = float(stats.get("avgdl") or 0.0) or 1.0

    # Prefix expansion mirrors the product: "auth" still finds "authentication".
    expanded: list[str] = []
    for term in terms:
        expanded.append(term)
        try:
            expanded.extend(expand_prefix(storage, scope, term)[:10])
        except Exception:  # noqa: BLE001 - the catalog is an optimisation
            continue
    unique_terms = list(dict.fromkeys(expanded))[:MAX_TERMS]

    scored: dict[str, dict[str, Any]] = {}
    for term in unique_terms:
        try:
            entry = read_term(storage, scope, term)
        except Exception:  # noqa: BLE001
            continue
        if not entry:
            continue
        df = int(entry.get("df") or 0)
        if df <= 0:
            continue
        idf = _idf(max(document_count, df), df)
        for posting in entry.get("postings") or []:
            chunk_id = str(posting.get("chunkId") or "")
            if not chunk_id:
                continue
            tf = float(posting.get("tf") or 0)
            dl = float(posting.get("dl") or 0) or 1.0
            score = idf * (tf * (BM25_K1 + 1)) / (tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl))
            row = scored.setdefault(chunk_id, {"chunkId": chunk_id, "score": 0.0})
            row["score"] += score
            row["parentId"] = posting.get("parentId") or row.get("parentId")
            row["docId"] = posting.get("docId") or row.get("docId")
    ordered = sorted(scored.values(), key=lambda item: item["score"], reverse=True)
    return ordered[:limit]


def _fuse(
    semantic: list[VectorMatch], lexical: list[dict[str, Any]], limit: int
) -> list[dict[str, Any]]:
    fused: dict[str, dict[str, Any]] = {}
    vector_meta: dict[str, dict[str, Any]] = {}

    for rank, match in enumerate(semantic, start=1):
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
        if row.get("parentId") and not entry.get("parentId"):
            entry["parentId"] = row["parentId"]

    ordered = sorted(fused.values(), key=lambda item: item["rrfScore"], reverse=True)
    for entry in ordered:
        entry.setdefault("metadata", vector_meta.get(entry["chunkId"], {}))
    return ordered[:limit]


def _to_passages(
    storage: Storage,
    scope: str,
    ordered: list[dict[str, Any]],
    query: str,
    *,
    allow_admin: bool = False,
) -> list[Passage]:
    parent_ids = [
        entry["parentId"] for entry in ordered if entry.get("parentId")
    ][:MAX_PARENTS]
    unique_parents = list(dict.fromkeys(parent_ids))
    parents: dict[str, dict[str, Any]] = {}
    if unique_parents:
        with ThreadPoolExecutor(max_workers=min(8, len(unique_parents))) as pool:
            for parent_id, data in pool.map(
                lambda pid: (pid, _load_parent(storage, scope, pid)), unique_parents
            ):
                if data:
                    parents[parent_id] = data

    terms = query_terms(query)
    passages: list[Passage] = []
    seen_parents: set[str] = set()
    for entry in ordered:
        parent_id = str(entry.get("parentId") or "")
        parent = parents.get(parent_id) if parent_id else None
        metadata = entry.get("metadata") or {}
        if parent is None and not metadata:
            continue
        if parent_id:
            if parent_id in seen_parents:
                continue
            seen_parents.add(parent_id)

        child_text = ""
        for child in (parent or {}).get("children") or []:
            if child.get("chunkId") == entry["chunkId"]:
                child_text = str(child.get("text") or "")
                break

        content = str((parent or {}).get("content") or "") or child_text or str(
            metadata.get("text") or ""
        )
        matched = child_text or str(metadata.get("text") or "") or content

        # The corpus carries its page route, title and audience in frontmatter,
        # which the shared indexer treats as plain text (it writes only kbId/status
        # as metadata). Parsing it here keeps citations linkable without forking the
        # pipeline. Fall back to any metadata an indexer happens to provide.
        front = parse_frontmatter(content)
        audience = str(
            front.get("audience") or (parent or {}).get("audience") or ""
        )
        if not _audience_allowed(audience, allow_admin=allow_admin):
            continue
        route = str(
            (parent or {}).get("route") or metadata.get("route") or front.get("route") or ""
        )
        title = str(
            (parent or {}).get("title")
            or metadata.get("title")
            or front.get("title")
            or (parent or {}).get("fileName")
            or metadata.get("fileName")
            or ""
        )
        raw_page = (parent or {}).get("page")
        passages.append(
            Passage(
                index=0,
                title=title,
                route=route,
                content=content,
                matched=matched,
                snippet=_snippet(matched or content, terms),
                score=float(entry.get("rrfScore") or 0.0),
                doc_id=str((parent or {}).get("docId") or metadata.get("docId") or ""),
                kb_id=str((parent or {}).get("kbId") or metadata.get("kbId") or ""),
                page=raw_page if isinstance(raw_page, int) else None,
                metadata={
                    "vectorScore": entry.get("vectorScore"),
                    "lexicalScore": entry.get("lexicalScore"),
                },
            )
        )
    for position, passage in enumerate(passages, start=1):
        passage.index = position
    return passages


def _cache_key(query: str, top_k: int, audience: str) -> str:
    # The audience is part of the key: without it an admin-scoped answer could be
    # served to a non-admin asking the same question.
    return cache.cache_key("avi-search", query.strip().lower(), top_k, audience)


def search(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    audience: str = "user",
    allow_admin: bool = False,
    use_cache: bool = True,
) -> tuple[list[Passage], dict[str, Any]]:
    """Hybrid search over the reserved platform scope.

    Returns ``(passages, diagnostic)``. Retrieval failure is **not** fatal: the
    caller gets an empty list plus a diagnostic and Avi answers "I don't have that
    documented" rather than erroring.
    """
    started = time.perf_counter()
    diagnostic: dict[str, Any] = {"query": query, "stage": "start"}
    text = (query or "").strip()
    if not text:
        return [], {**diagnostic, "stage": "empty-query"}

    scope = settings.retrieval_scope()
    key = _cache_key(text, top_k, audience)
    if use_cache:
        cached = cache.get(key)
        if isinstance(cached, list) and cached:
            passages = [_passage_from_dict(item) for item in cached]
            return passages, {
                **diagnostic,
                "stage": "cache-hit",
                "count": len(passages),
                "latencyMs": int((time.perf_counter() - started) * 1000),
            }

    try:
        storage = Storage()
        store = vector_store(storage)
        vectors = embed_texts([text], load_config())
        query_vector = list(vectors[0]) if vectors else []
    except Exception as exc:  # noqa: BLE001 - degrade to "not documented"
        return [], {
            **diagnostic,
            "stage": "embed-failed",
            "error": f"{type(exc).__name__}: {exc}",
            "latencyMs": int((time.perf_counter() - started) * 1000),
        }

    if not query_vector:
        return [], {**diagnostic, "stage": "no-vector"}

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            semantic_future = pool.submit(
                store.query,
                scope,
                query_vector,
                SEMANTIC_TOP_K,
                _vector_filter(settings.platform_kb_id()),
            )
            lexical_future = pool.submit(_lexical_leg, storage, scope, text, SEMANTIC_TOP_K)
            semantic = semantic_future.result()
            lexical = lexical_future.result()
    except Exception as exc:  # noqa: BLE001
        # One leg failing must not lose the other: retry them independently.
        # One leg failing must not lose the other, and it must not be silent: a
        # leg that returns nothing looks identical to "the corpus has no answer",
        # which is exactly how a mistyped filter or a missing dependency hides. So
        # each leg's failure is recorded on the diagnostic (and therefore on the
        # turn's trace) instead of being swallowed.
        errors: list[str] = []
        try:
            semantic = store.query(
                scope,
                query_vector,
                SEMANTIC_TOP_K,
                _vector_filter(settings.platform_kb_id()),
            )
        except Exception as leg_exc:  # noqa: BLE001
            semantic = []
            errors.append(f"semantic: {type(leg_exc).__name__}: {leg_exc}")
        try:
            lexical = _lexical_leg(storage, scope, text, SEMANTIC_TOP_K)
        except Exception as leg_exc:  # noqa: BLE001
            lexical = []
            errors.append(f"lexical: {type(leg_exc).__name__}: {leg_exc}")
        diagnostic["degraded"] = f"{type(exc).__name__}: {exc}"
        if errors:
            diagnostic["legErrors"] = errors

    fused = _fuse(semantic, lexical, max(top_k * 3, top_k))
    passages = _to_passages(
        storage, scope, fused, text, allow_admin=allow_admin
    )[: max(1, top_k)]

    diagnostic.update(
        {
            "stage": "ok",
            "semantic": len(semantic),
            "lexical": len(lexical),
            "fused": len(fused),
            "returned": len(passages),
            "latencyMs": int((time.perf_counter() - started) * 1000),
            "scope": scope,
        }
    )
    if diagnostic.get("legErrors"):
        diagnostic["stage"] = "degraded"
    if use_cache and passages:
        try:
            cache.set(
                key,
                [passage.to_dict() for passage in passages],
                ttl_seconds=CACHE_TTL_SECONDS,
            )
        except Exception:  # noqa: BLE001 - the cache is never on the critical path
            pass
    return passages, diagnostic


def _passage_from_dict(item: dict[str, Any]) -> Passage:
    return Passage(
        index=int(item.get("index") or 0),
        title=str(item.get("title") or ""),
        route=str(item.get("route") or ""),
        content=str(item.get("content") or ""),
        matched=str(item.get("matchedContent") or ""),
        snippet=str(item.get("snippet") or ""),
        score=float(item.get("score") or 0.0),
        doc_id=str(item.get("documentId") or ""),
        kb_id=str(item.get("knowledgeBaseId") or ""),
        page=item.get("page") if isinstance(item.get("page"), int) else None,
    )


def as_prompt_passages(passages: list[Passage]) -> list[dict[str, Any]]:
    """The shape :mod:`avi.prompts` expects."""
    return [
        {
            "index": passage.index,
            "title": passage.title,
            "route": passage.route,
            "content": passage.matched or passage.content,
        }
        for passage in passages
    ]


def debug_dump(passages: list[Passage]) -> str:
    return json.dumps([passage.to_dict() for passage in passages], indent=2)[:4_000]
