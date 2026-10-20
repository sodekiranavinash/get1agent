"""Graph RAG augmentation: seed entities → multi-hop traversal → parent chunks.

Graph RAG is **additive**: the hybrid legs are untouched, and this module extra
fts the entities/relationships that the knowledge base's graph holds (built at
ingest time) to widen and explain the result set.

The flow is the standard GraphRAG query pattern:

1. **Seed** — find the entities the query is about, two ways: a vector search over
   the entity's own embeddings (paraphrase-tolerant) and a lexical lookup of the
   query's tokens in the entity-name index (precise, cheap).
2. **Traverse** — walk the graph from the seeds, score-decayed by hop distance,
   capped by node/edge/fan-out budgets so the cost stays bounded.
3. **Resolve** — every visited node carries the ``parentIds``/``chunkIds`` where
   it was seen, so a graph hit resolves to the *same* parent objects the hybrid
   legs hydrate (small-to-big, one ``GetObject`` per parent).
4. **Explain** — the relationships among the visited nodes ride along, so the
   caller can show *why* a passage is relevant (Alice —WORKS_AT→ Acme).

Graph candidates fuse with the hybrid candidates by carrying an RRF-equivalent
``rrfScore`` (``GRAPH_WEIGHT × decayed seed score``), so the existing ordering,
rerank and per-document cap apply unchanged.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from retrieval import graph as graph_store
from retrieval.layout import query_terms
from retrieval.s3_vectors import VectorStore
from core.storage import Storage
from src.search.hybrid import _load_parent, _snippet

GRAPH_ENABLED = (os.environ.get("GRAPH_RETRIEVAL_ENABLED", "true") or "true").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)
GRAPH_HOPS = int(os.environ.get("GRAPH_HOPS", "2"))
GRAPH_SEED_TOP_K = int(os.environ.get("GRAPH_SEED_TOP_K", "12"))
GRAPH_SEED_TOP_N = int(os.environ.get("GRAPH_SEED_TOP_N", "8"))
GRAPH_MAX_NODES = int(os.environ.get("GRAPH_MAX_NODES", "60"))
GRAPH_MAX_EDGES = int(os.environ.get("GRAPH_MAX_EDGES", "120"))
GRAPH_MAX_FANOUT = int(os.environ.get("GRAPH_MAX_FANOUT", "24"))
GRAPH_DECAY = float(os.environ.get("GRAPH_DECAY", "0.7"))
GRAPH_WEIGHT = float(os.environ.get("GRAPH_WEIGHT", "0.5"))
GRAPH_MAX_RELATIONSHIPS = int(os.environ.get("GRAPH_MAX_RELATIONSHIPS", "40"))
GRAPH_MAX_PARENTS = int(os.environ.get("GRAPH_MAX_PARENTS", "30"))


def enabled() -> bool:
    return GRAPH_ENABLED


def _lexical_seeds(storage: Storage, sub: str, query: str, kb_ids: list[str]) -> dict[str, float]:
    """Entity nodes whose name tokens appear in the query (prefix-expanded)."""
    terms = query_terms(query)
    if not terms:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(terms))) as pool:
        expansions = list(
            pool.map(lambda term: graph_store.expand_entity_prefix(storage, sub, term), terms)
        )
    tokens: list[str] = []
    seen: set[str] = set()
    for group in expansions:
        for token in group:
            if token not in seen:
                seen.add(token)
                tokens.append(token)
    if not tokens:
        return {}

    with ThreadPoolExecutor(max_workers=min(8, len(tokens))) as pool:
        shards = list(
            pool.map(lambda token: graph_store.read_entity_term(storage, sub, token), tokens)
        )
    kb_filter = set(kb_ids) if kb_ids else None
    counts: dict[str, int] = {}
    for shard in shards:
        for entry in shard:
            node_id = str(entry.get("nodeId") or "")
            if not node_id:
                continue
            counts[node_id] = counts.get(node_id, 0) + 1
    if not counts:
        return {}
    peak = max(counts.values())
    return {node_id: count / peak for node_id, count in counts.items()}


def _vector_seeds(
    store: VectorStore, sub: str, query_vector: list[float], kb_ids: list[str]
) -> dict[str, float]:
    try:
        matches = store.query(
            sub,
            query_vector,
            GRAPH_SEED_TOP_K,
            filters=graph_store.entity_vector_filters(kb_ids),
        )
    except Exception:  # noqa: BLE001 - seeding is best-effort
        return {}
    seeds: dict[str, float] = {}
    for match in matches:
        node_id = str((match.metadata or {}).get("nodeId") or "").strip()
        if not node_id:
            continue
        seeds[node_id] = max(seeds.get(node_id, 0.0), float(match.score))
    return seeds


def _seed_entities(
    storage: Storage,
    store: VectorStore,
    sub: str,
    *,
    query: str,
    query_vector: list[float],
    kb_ids: list[str],
) -> dict[str, float]:
    vector_seeds = _vector_seeds(store, sub, query_vector, kb_ids)
    lexical_seeds = _lexical_seeds(storage, sub, query, kb_ids)

    combined: dict[str, float] = {}
    for node_id, score in vector_seeds.items():
        combined[node_id] = max(combined.get(node_id, 0.0), score)
    for node_id, score in lexical_seeds.items():
        # Lexical is precise but not similarity-scaled: keep it below a strong
        # semantic seed so an exact name match does not drown a better context.
        combined[node_id] = max(combined.get(node_id, 0.0), 0.5 + 0.5 * score)

    if not combined:
        return {}
    ordered = sorted(combined.items(), key=lambda item: item[1], reverse=True)
    return dict(ordered[: max(1, GRAPH_SEED_TOP_N)])


def search_graph(
    storage: Storage,
    store: VectorStore,
    sub: str,
    *,
    query: str,
    query_vector: list[float],
    kb_ids: list[str],
    allowed_doc_ids: set[str] | None = None,
    limit: int = GRAPH_MAX_PARENTS,
) -> dict[str, Any]:
    """Graph-augmented candidates + the relationships that produced them."""
    empty = {
        "candidates": [],
        "relationships": [],
        "meta": {"enabled": True, "seeds": 0, "nodes": 0, "edges": 0, "relations": 0},
    }
    if not enabled() or not kb_ids or not query_vector:
        return empty

    stats = graph_store.read_stats(storage, sub)
    if int(stats.get("nodeCount") or 0) <= 0:
        return empty

    seeds = _seed_entities(
        storage, store, sub, query=query, query_vector=query_vector, kb_ids=kb_ids
    )
    if not seeds:
        return empty

    walked = graph_store.traverse(
        storage,
        sub,
        seeds,
        kb_ids=kb_ids,
        hops=GRAPH_HOPS,
        max_nodes=GRAPH_MAX_NODES,
        max_edges=GRAPH_MAX_EDGES,
        max_fanout=GRAPH_MAX_FANOUT,
        decay=GRAPH_DECAY,
    )
    nodes = walked.get("nodes") or []
    if not nodes:
        return {**empty, "meta": {**empty["meta"], "seeds": len(seeds)}}

    # Map each parent to its best-scoring node (a parent can host several).
    parent_nodes: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if allowed_doc_ids is not None and not _node_allowed(node, allowed_doc_ids):
            continue
        for parent_id in node.get("parentIds") or []:
            existing = parent_nodes.get(parent_id)
            if existing is None or float(node["score"]) > float(existing["score"]):
                parent_nodes[parent_id] = node

    parent_ids = list(parent_nodes.keys())[: max(1, min(limit, GRAPH_MAX_PARENTS))]
    parents: dict[str, dict[str, Any]] = {}
    if parent_ids:
        with ThreadPoolExecutor(max_workers=min(8, len(parent_ids))) as pool:
            loaded = list(
                pool.map(lambda pid: (pid, _load_parent(storage, sub, pid)), parent_ids)
            )
        parents = {pid: data for pid, data in loaded if data}

    terms = query_terms(query)
    candidates: list[dict[str, Any]] = []
    for parent_id in parent_ids:
        parent = parents.get(parent_id)
        if not parent:
            continue
        node = parent_nodes[parent_id]
        children = parent.get("children") or []
        child = None
        for item in children:
            if item.get("chunkId") in (node.get("chunkIds") or []):
                child = item
                break
        matched_content = (
            (child or {}).get("text")
            or node.get("description")
            or parent.get("content")
            or ""
        )
        score = float(node["score"])
        candidates.append(
            {
                "chunkId": (child or {}).get("chunkId")
                or (node.get("chunkIds") or [parent_id])[0],
                "documentId": parent.get("docId"),
                "knowledgeBaseId": parent.get("kbId"),
                "kbName": parent.get("kbName"),
                "fileName": parent.get("fileName"),
                "contentType": parent.get("contentType"),
                "page": parent.get("page")
                if parent.get("page") is not None
                else (child or {}).get("page"),
                "pageEnd": parent.get("pageEnd")
                if parent.get("pageEnd") is not None
                else (child or {}).get("pageEnd"),
                "ordinal": (child or {}).get("ordinal"),
                "parentId": parent_id,
                "content": parent.get("content") or matched_content,
                "matchedContent": matched_content,
                "snippet": _snippet(matched_content, terms),
                # Fuse with the hybrid candidates on the RRF scale.
                "rrfScore": GRAPH_WEIGHT * score,
                "graphScore": score,
                "graphNode": node.get("name"),
                "graphNodeType": node.get("type"),
                "graphHop": node.get("hop"),
                "source": "graph",
            }
        )

    relationships = _relationships(nodes, walked.get("edges") or [])
    return {
        "candidates": candidates,
        "relationships": relationships,
        "meta": {
            "enabled": True,
            "hops": GRAPH_HOPS,
            "seeds": len(seeds),
            "nodes": len(nodes),
            "edges": len(walked.get("edges") or []),
            "relations": len(relationships),
            "parents": len(candidates),
            "kbIds": kb_ids,
        },
    }


def _node_allowed(node: dict[str, Any], allowed_doc_ids: set[str]) -> bool:
    doc_ids = node.get("docIds") or []
    if not doc_ids:
        return True
    return any(str(doc_id) in allowed_doc_ids for doc_id in doc_ids)


def _relationships(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    hop_by_node = {node["nodeId"]: int(node.get("hop") or 0) for node in nodes}
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in edges:
        subject = str(edge.get("subject") or "").strip()
        predicate = str(edge.get("predicate") or "").strip()
        obj = str(edge.get("object") or "").strip()
        if not subject or not predicate or not obj:
            continue
        key = (subject.lower(), predicate.lower(), obj.lower())
        if key in seen:
            continue
        seen.add(key)
        hop = min(
            hop_by_node.get(edge.get("from"), 99),
            hop_by_node.get(edge.get("to"), 99),
        )
        out.append(
            {
                "subject": subject,
                "predicate": predicate,
                "object": obj,
                "description": edge.get("description") or "",
                "weight": float(edge.get("weight") or 1.0),
                "knowledgeBaseId": edge.get("kbId"),
                "documentId": edge.get("docId"),
                "chunkId": edge.get("chunkId"),
                "hop": hop if hop != 99 else None,
            }
        )
    out.sort(key=lambda item: (item["hop"] if item["hop"] is not None else 99, -item["weight"]))
    return out[:GRAPH_MAX_RELATIONSHIPS]
