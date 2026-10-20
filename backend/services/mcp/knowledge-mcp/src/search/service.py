"""Retrieval orchestration for the knowledge MCP tools (DynamoDB + S3 + vectors)."""

from __future__ import annotations

from typing import Any

from data.repositories import knowledge_bases as kb_repo
from data.repositories import tags as tags_repo
from src.search import graph as graph_retrieval
from src.search.errors import RetrievalError
from src.search.hybrid import DEFAULT_CANDIDATE_LIMIT, search_candidates
from retrieval.s3_vectors import vector_store
from core.storage import Storage
from data.repositories.users import get_user_by_id

MAX_CANDIDATE_LIMIT = 200
VALID_TAG_MATCH = ("any", "all")


def _interleave(
    first: list[dict[str, Any]], second: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Alternate two independently ranked lists, keeping each one's order.

    A mixed request (Graph + Hybrid knowledge bases) must surface both: their
    scores live on different scales, so concatenating or score-sorting one list
    would bury the other. Each KB's own strategy still decides its internal rank.
    """
    if not first:
        return list(second)
    if not second:
        return list(first)
    merged: list[dict[str, Any]] = []
    for index in range(max(len(first), len(second))):
        if index < len(first):
            merged.append(first[index])
        if index < len(second):
            merged.append(second[index])
    return merged


def _retrieval_mode(kb: dict[str, Any]) -> str:
    mode = str(kb.get("retrievalMode") or "hybrid").strip().lower()
    return mode if mode in ("hybrid", "graph") else "hybrid"


def _clean_names(names: Any) -> list[str]:
    if not isinstance(names, (list, tuple)):
        return []
    return [str(name).strip() for name in names if str(name).strip()]


def _clean_ids(ids: Any) -> list[str]:
    if not isinstance(ids, (list, tuple)):
        return []
    return [str(value).strip() for value in ids if str(value).strip()]


def resolve_knowledge_bases(
    sub: str,
    names: Any = None,
    ids: Any = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Resolve a caller's KBs by name (case-insensitive) or id.

    Returns ``(matched, not_found_names)``. With neither names nor ids, every
    knowledge base owned by the user is returned.
    """
    name_list = _clean_names(names)
    id_list = set(_clean_ids(ids))
    lower_names = {name.lower() for name in name_list}

    matched: list[dict[str, Any]] = []
    for kb in kb_repo.list_kbs(sub):
        name_matches = kb.get("name", "").lower() in lower_names
        id_matches = kb.get("kbId") in id_list
        if name_list or id_list:
            if name_matches or id_matches:
                matched.append(kb)
        else:
            matched.append(kb)

    matched_names = {kb.get("name", "").lower() for kb in matched}
    not_found = [name for name in name_list if name.lower() not in matched_names]
    matched.sort(key=lambda item: item.get("name", ""))
    return matched, not_found


def _serialize_discovery_kb(
    kb: dict[str, Any], tags: list[dict[str, str]]
) -> dict[str, Any]:
    return {
        "name": kb.get("name"),
        "description": kb.get("description"),
        "tags": tags,
    }


def list_knowledge_bases(sub: str, names: Any = None) -> dict[str, Any]:
    """Backing query for the ``get-user-knowledge-bases`` tool."""
    user = get_user_by_id(sub)
    if user is None:
        raise RetrievalError("user_not_found", "No account found for this user", 404)

    matched, not_found = resolve_knowledge_bases(sub, names)
    # Only ready knowledge bases are searchable, so only those are discoverable.
    matched = [kb for kb in matched if kb.get("status") == "ready"]
    tags_by_kb = tags_repo.list_tags_by_kb(sub)
    return {
        "knowledgeBases": [
            _serialize_discovery_kb(kb, tags_by_kb.get(kb["kbId"], []))
            for kb in matched
        ],
        "notFound": not_found,
    }


def _tag_document_filter(
    sub: str, tags: list[str], tag_match: str
) -> set[str] | None:
    if not tags:
        return None
    sets = [tags_repo.document_ids_for_tag(sub, tag) for tag in tags]
    if tag_match == "all":
        result = set.intersection(*sets) if sets else set()
    else:
        result = set.union(*sets) if sets else set()
    return result


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
                "contentType": candidate.get("contentType"),
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


def search(
    sub: str,
    query: str,
    query_vector: list[float],
    *,
    knowledge_base_names: Any = None,
    knowledge_base_ids: Any = None,
    tags: Any = None,
    tag_match: str = "any",
    limit: int = DEFAULT_CANDIDATE_LIMIT,
    allowed_doc_ids: set[str] | None = None,
    graph: bool | None = None,
) -> dict[str, Any]:
    """Run hybrid search and return candidates + per-KB metadata + warnings.

    ``graph`` selects the retrieval strategy for Graph-mode knowledge bases:
    ``None`` follows each base's own ``retrievalMode`` (a Graph KB answers
    graph-first), ``True`` forces graph-first, ``False`` forces the hybrid legs.
    Graph-first means seed entities → traverse → the passages those entities were
    seen in; when the graph has nothing for the query the hybrid legs answer it
    instead (``meta.graph.fallback``). Hybrid-mode KBs always use the hybrid legs.
    """
    user = get_user_by_id(sub)
    if user is None:
        raise RetrievalError("user_not_found", "No account found for this user", 404)

    matched, not_found = resolve_knowledge_bases(
        sub, knowledge_base_names, knowledge_base_ids
    )
    warnings: list[str] = []
    if not_found:
        warnings.append(f"Unknown knowledge bases: {', '.join(not_found)}")

    dimension = len(query_vector)
    eligible: list[dict[str, Any]] = []
    for kb in matched:
        if kb.get("status") != "ready":
            warnings.append(f'Knowledge base "{kb.get("name")}" is {kb.get("status")}; skipped')
            continue
        if int(kb.get("embeddingDim") or 0) != dimension:
            warnings.append(
                f'Knowledge base "{kb.get("name")}" uses '
                f'{kb.get("embeddingDim")}-dim vectors; skipped'
            )
            continue
        eligible.append(kb)

    if not eligible:
        return {
            "candidates": [],
            "knowledgeBases": [],
            "notFound": not_found,
            "warnings": warnings,
            "relationships": [],
            "graph": {"enabled": False},
        }

    tag_list = [str(tag) for tag in tags] if isinstance(tags, (list, tuple)) else []
    if tag_list and allowed_doc_ids is None:
        allowed_doc_ids = _tag_document_filter(sub, tag_list, tag_match)

    storage = Storage()
    store = vector_store(storage)

    # Each knowledge base is searched the way it was created: a Graph-mode KB
    # through its graph, a Hybrid-mode KB through the vector + BM25 legs. The two
    # are **separate paths** (nothing is fused): a Graph KB only falls back to the
    # hybrid legs when its graph has nothing for this query, and a Hybrid KB never
    # touches the graph. When a request spans both kinds, each contributes its own
    # results (interleaved, so neither list is buried by the other).
    graph_kbs = [kb for kb in eligible if _retrieval_mode(kb) == "graph"]
    hybrid_kbs = [kb for kb in eligible if _retrieval_mode(kb) != "graph"]
    graph_ids = [kb["kbId"] for kb in graph_kbs]
    # ``graph=False`` opts the Graph KBs out for this request: they are searched
    # with the hybrid legs like any other KB.
    graph_first = bool(graph_ids) and (graph is None or bool(graph))
    graph_ran = bool(graph_first) and graph_retrieval.enabled()

    relationships: list[dict[str, Any]] = []
    graph_meta: dict[str, Any] = {"enabled": False}
    graph_candidates: list[dict[str, Any]] = []

    if graph_ran:
        graph_result = graph_retrieval.search_graph(
            storage,
            store,
            sub,
            query=query,
            query_vector=query_vector,
            kb_ids=graph_ids,
            allowed_doc_ids=allowed_doc_ids,
            limit=max(limit, 1),
        )
        relationships = graph_result.get("relationships") or []
        graph_meta = {
            **(graph_result.get("meta") or {"enabled": True}),
            "requested": True,
            "strategy": "graph",
            "fallback": False,
            "knowledgeBases": graph_ids,
        }
        graph_candidates = sorted(
            graph_result.get("candidates") or [],
            key=lambda item: float(item.get("rrfScore") or 0.0),
            reverse=True,
        )

    # The graph had nothing (or is off/opted out): the Graph KBs join the hybrid
    # legs so the query is still answered — and the payload says it fell back.
    graph_fallback = bool(graph_ids) and not graph_candidates
    hybrid_ids = [kb["kbId"] for kb in hybrid_kbs] + (graph_ids if graph_fallback else [])
    if graph_fallback:
        counts = {
            key: graph_meta[key]
            for key in ("seeds", "nodes", "edges", "parents")
            if key in graph_meta
        }
        seeds_found = int(graph_meta.get("seeds") or 0)
        reason = (
            "graph not requested"
            if not graph_first
            else "graph disabled"
            if not graph_ran
            else "no linked passages"
            if seeds_found
            else "no matching entities"
        )
        graph_meta = {
            **counts,
            "enabled": graph_ran,
            "requested": bool(graph_first),
            "strategy": "graph" if graph_first else "hybrid",
            # An explicit opt-out is not a fallback: the graph never ran.
            "fallback": bool(graph_first),
            "reason": reason,
            "knowledgeBases": graph_ids,
        }

    hybrid_candidates = (
        search_candidates(
            storage,
            store,
            sub,
            kb_ids=hybrid_ids,
            query=query,
            query_vector=query_vector,
            limit=limit,
            allowed_doc_ids=allowed_doc_ids,
        )
        if hybrid_ids
        else []
    )
    candidates = _interleave(graph_candidates, hybrid_candidates)

    return {
        "candidates": candidates,
        "knowledgeBases": [
            {
                "id": kb["kbId"],
                "name": kb.get("name"),
                "status": kb.get("status"),
                "retrievalMode": _retrieval_mode(kb),
            }
            for kb in eligible
        ],
        "notFound": not_found,
        "warnings": warnings,
        "relationships": relationships,
        "graph": graph_meta,
    }
