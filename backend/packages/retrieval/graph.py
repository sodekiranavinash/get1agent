"""S3-backed knowledge graph for Graph RAG.

There is **no external graph database** — the graph is plain S3 JSON read with
``GetObject`` under ``index/<userId>/graph/``:

```
index/<userId>/graph/nodes/<nodeId>.json     entity node (name, type, description, provenance)
index/<userId>/graph/adj/<nodeId>.json       adjacency (both directions) + relationship facts
index/<userId>/graph/enames/<token>.json     inverted index of entity-name tokens
index/<userId>/graph/ecat/<c0>.json          entity-name token catalog (prefix expansion)
index/<userId>/graph/docs/<docId>.json       what one document contributed (idempotent delete)
index/<userId>/graph/stats.json              nodeCount, edgeCount, docCount
```

Two layers, as in the GraphRAG pattern catalog: the **lexical layer** (documents
and chunks, already in the vector store + term index) and the **knowledge layer**
(entities and their typed relationships, here). ``MENTIONED_IN`` is implicit — a
node carries the ``parentIds``/``chunkIds`` where it was seen, so a graph hit
resolves straight to the same parent objects hybrid retrieval hydrates.

Relationships follow the LightRAG / FalkorDB shape: **one generic edge** (a single
object per triple) carrying a ``type`` predicate property, rather than one graph
relationship type per predicate. An edge is stored symmetrically — the same edge
id appears in both endpoints' adjacency objects with a ``direction`` — so one
``GetObject`` per hop yields the full neighbourhood.

Writes are read-modify-write with a conditional ``If-Match`` PUT and bounded
exponential backoff (the same primitive the term index uses), so two documents
indexing concurrently never lose updates.
"""

from __future__ import annotations

import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from typing import Any, Callable

from retrieval.layout import (
    graph_adjacency_key,
    graph_doc_key,
    graph_entity_catalog_key,
    graph_entity_term_key,
    graph_node_key,
    graph_stats_key,
    tokenize,
)
from retrieval.s3_vectors import VectorRecord, VectorStore
from core.storage import PreconditionFailed, Storage

# Metadata discriminator for entity vectors living in the same per-user vector
# index as the chunk vectors. Chunk search filters ``status="ready"``, so entity
# vectors must NOT carry that status or they would surface as chunk hits.
ENTITY_VECTOR_KIND = "entity"

_MAX_ATTEMPTS = 6
_BASE_BACKOFF_SECONDS = 0.05
_MAX_BACKOFF_SECONDS = 2.0
# Entity/edge writes are independent keys, so fan them out — a document can
# contribute hundreds of entities and triples. Tunable so a slow/emulated S3
# (Floci) can dial the fan-out down without a code branch.
_WRITE_MAX_WORKERS = max(1, int(os.environ.get("GRAPH_WRITE_WORKERS") or 16))
# Cap on entity-name tokens kept for one entity (long names are rare).
_MAX_NAME_TOKENS = 8
# Cap entity-name prefix expansion so one prefix cannot fan out into thousands
# of GETs (mirrors the term index).
MAX_PREFIX_EXPANSION = 50

_NAME_CLEAN_RE = re.compile(r"[^\w\s&-]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_name(name: str) -> str:
    """Case/space/punctuation-normalised entity name (the merge key)."""
    text = _NAME_CLEAN_RE.sub(" ", (name or "").lower())
    return _WS_RE.sub(" ", text).strip()


def node_id(name: str, entity_type: str = "") -> str:
    """Deterministic, type-qualified node id: ``e_<sha1[:16]>``.

    Qualifying by type keeps "Jordan" (Person) and "Jordan" (Location) apart.
    """
    digest = hashlib.sha1(
        f"{(entity_type or 'other').strip().lower()}:{normalize_name(name)}".encode("utf-8")
    ).hexdigest()[:16]
    return f"e_{digest}"


def edge_id(from_id: str, rel_type: str, to_id: str) -> str:
    digest = hashlib.sha1(
        f"{from_id}|{(rel_type or 'RELATED_TO').strip().upper()}|{to_id}".encode("utf-8")
    ).hexdigest()[:20]
    return f"r_{digest}"


def name_tokens(name: str) -> list[str]:
    """Tokens of an entity name used to build the inverted name index."""
    tokens = tokenize(name or "")
    return list(dict.fromkeys(tokens))[:_MAX_NAME_TOKENS]


def _run_parallel(fn: Callable[[Any], Any], items: list[Any]) -> list[Any]:
    if not items:
        return []
    if len(items) == 1 or _WRITE_MAX_WORKERS == 1:
        return [fn(item) for item in items]
    with ThreadPoolExecutor(max_workers=min(_WRITE_MAX_WORKERS, len(items))) as pool:
        return list(pool.map(fn, items))


def _read_modify_write(
    storage: Storage,
    key: str,
    mutate: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for attempt in range(_MAX_ATTEMPTS):
        try:
            data, etag = storage.get_json_with_etag(key)
            last = mutate(dict(data or {}))
            storage.put_json_conditional(key, last, etag)
            return last
        except PreconditionFailed:
            # Another writer won the race; re-read and try again.
            pass
        except Exception:  # noqa: BLE001 - transient S3 errors are retried
            # A busy endpoint can answer a read/write with a timeout or 5xx.
            # Retrying is safe here because every mutation is idempotent, but a
            # persistent failure must still surface on the last attempt.
            if attempt == _MAX_ATTEMPTS - 1:
                raise
        time.sleep(
            min(_MAX_BACKOFF_SECONDS, _BASE_BACKOFF_SECONDS * 2**attempt)
        )
    raise PreconditionFailed(key)


def _add_unique(items: list[Any], value: Any) -> None:
    if value is None or value == "":
        return
    if value not in items:
        items.append(value)


# --- reads -------------------------------------------------------------------


def read_node(storage: Storage, sub: str, node_id_: str) -> dict[str, Any] | None:
    data, _ = storage.get_json_with_etag(graph_node_key(sub, node_id_))
    return data


def read_adjacency(storage: Storage, sub: str, node_id_: str) -> dict[str, Any] | None:
    data, _ = storage.get_json_with_etag(graph_adjacency_key(sub, node_id_))
    return data


def load_nodes(
    storage: Storage, sub: str, node_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """One GET per node, fanned out."""
    unique = list(dict.fromkeys(node_ids))
    if not unique:
        return {}
    loaded = _run_parallel(
        lambda nid: (nid, read_node(storage, sub, nid)), unique
    )
    return {nid: data for nid, data in loaded if data}


def load_adjacencies(
    storage: Storage, sub: str, node_ids: list[str]
) -> dict[str, dict[str, Any]]:
    unique = list(dict.fromkeys(node_ids))
    if not unique:
        return {}
    loaded = _run_parallel(
        lambda nid: (nid, read_adjacency(storage, sub, nid)), unique
    )
    return {nid: data for nid, data in loaded if data}


def read_stats(storage: Storage, sub: str) -> dict[str, Any]:
    data, _ = storage.get_json_with_etag(graph_stats_key(sub))
    if not data:
        return {"nodeCount": 0, "edgeCount": 0, "docCount": 0}
    return data


def graph_exists(storage: Storage, sub: str) -> bool:
    return int(read_stats(storage, sub).get("nodeCount") or 0) > 0


def read_entity_term(storage: Storage, sub: str, token: str) -> list[dict[str, Any]]:
    data, _ = storage.get_json_with_etag(graph_entity_term_key(sub, token))
    nodes = (data or {}).get("nodes")
    return nodes if isinstance(nodes, list) else []


def expand_entity_prefix(storage: Storage, sub: str, term: str) -> list[str]:
    """Exact term plus entity-name tokens starting with it (prefix match)."""
    if not term:
        return []
    data, _ = storage.get_json_with_etag(graph_entity_catalog_key(sub, term[0]))
    tokens = (data or {}).get("tokens") if isinstance(data, dict) else None
    if not isinstance(tokens, list):
        return [term]
    matches = [str(token) for token in tokens if str(token).startswith(term)]
    if term not in matches:
        matches.append(term)
    return matches[:MAX_PREFIX_EXPANSION]


# --- writes ------------------------------------------------------------------


def _merge_node(
    storage: Storage,
    sub: str,
    *,
    kb_id: str,
    doc_id: str,
    node: dict[str, Any],
) -> tuple[str, bool]:
    nid = str(node["nodeId"])
    key = graph_node_key(sub, nid)
    created = {"new": False}

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        if not data:
            created["new"] = True
            data = {
                "nodeId": nid,
                "name": node.get("name") or "",
                "type": node.get("type") or "Other",
                "description": "",
                "kbIds": [],
                "docIds": [],
                "chunkIds": [],
                "parentIds": [],
                "tokens": name_tokens(node.get("name") or ""),
            }
        _add_unique(data.setdefault("kbIds", []), kb_id)
        _add_unique(data.setdefault("docIds", []), doc_id)
        for chunk in node.get("chunkIds") or []:
            _add_unique(data.setdefault("chunkIds", []), chunk)
        for parent in node.get("parentIds") or []:
            _add_unique(data.setdefault("parentIds", []), parent)
        description = str(node.get("description") or "").strip()
        if description and len(description) > len(data.get("description") or ""):
            data["description"] = description
        if node.get("name") and not data.get("name"):
            data["name"] = node["name"]
        if node.get("type") and not data.get("type"):
            data["type"] = node["type"]
        data["updatedAt"] = _now()
        return data

    _read_modify_write(storage, key, mutate)
    return nid, created["new"]


def _index_token_postings(
    storage: Storage,
    sub: str,
    token_nodes: dict[str, dict[str, dict[str, Any]]],
) -> None:
    """Write the entity-name inverted index, one read-modify-write per token.

    ``token_nodes`` maps a token to the entities (by nodeId) that use it. A
    document's entities frequently share tokens, so grouping first means a hot
    token is written once, not once per entity that happens to use it — fewer
    S3 calls and no intra-document contention on the same key.
    """

    def write_token(token: str) -> None:
        entries = token_nodes[token]
        key = graph_entity_term_key(sub, token)

        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            nodes = [
                entry
                for entry in (data.get("nodes") or [])
                if entry.get("nodeId") not in entries
            ]
            for nid, node in entries.items():
                nodes.append(
                    {
                        "nodeId": nid,
                        "name": node.get("name") or "",
                        "type": node.get("type") or "Other",
                    }
                )
            return {"nodes": nodes}

        _read_modify_write(storage, key, mutate)

    _run_parallel(write_token, list(token_nodes))


def _update_entity_catalog(storage: Storage, sub: str, tokens: list[str]) -> None:
    shards: dict[str, set[str]] = {}
    for token in tokens:
        if token:
            shards.setdefault(token[0], set()).add(token)
    for first_char, values in shards.items():
        key = graph_entity_catalog_key(sub, first_char)

        def mutate(data: dict[str, Any], values=values) -> dict[str, Any]:
            existing = set(data.get("tokens") or [])
            existing.update(values)
            return {"tokens": sorted(existing)}

        _read_modify_write(storage, key, mutate)


def _merge_evidence(
    existing: list[dict[str, Any]], incoming: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    out = [dict(item) for item in existing]
    for item in incoming:
        key = (item.get("docId"), item.get("chunkId"), item.get("parentId"))
        if not any(
            (entry.get("docId"), entry.get("chunkId"), entry.get("parentId")) == key
            for entry in out
        ):
            out.append(dict(item))
    return out


def _merge_edge_endpoints(
    storage: Storage, sub: str, endpoint_id: str, entries: list[dict[str, Any]]
) -> None:
    """Merge every edge entry an endpoint owns in one read-modify-write.

    A hub entity can be an endpoint of dozens of edges; writing it once per edge
    made concurrent writers collide on the same adjacency key (precondition
    failures). Grouping means one write per endpoint per document.
    """
    key = graph_adjacency_key(sub, endpoint_id)

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        if not data:
            data = {"nodeId": endpoint_id, "edges": []}
        edges = {item.get("id"): dict(item) for item in (data.get("edges") or [])}
        for entry in entries:
            existing = edges.get(entry["id"])
            if existing:
                merged = {
                    **existing,
                    **entry,
                    "evidence": _merge_evidence(
                        existing.get("evidence") or [], entry.get("evidence") or []
                    ),
                }
                merged["weight"] = max(
                    float(existing.get("weight") or 1.0),
                    float(entry.get("weight") or 1.0),
                )
                edges[entry["id"]] = merged
            else:
                edges[entry["id"]] = entry
        data["edges"] = list(edges.values())
        return data

    _read_modify_write(storage, key, mutate)


def _edge_endpoint_entry(
    edge: dict[str, Any], *, endpoint: str
) -> dict[str, Any]:
    """Build the adjacency entry as seen from one endpoint."""
    is_out = endpoint == edge["from"]
    other = edge["to"] if is_out else edge["from"]
    other_name = edge.get("toName") if is_out else edge.get("fromName")
    other_type = edge.get("toType") if is_out else edge.get("fromType")
    return {
        "id": edge["edgeId"],
        "direction": "out" if is_out else "in",
        "neighbor": other,
        "neighborName": other_name,
        "neighborType": other_type,
        "from": edge["from"],
        "to": edge["to"],
        "fromName": edge.get("fromName"),
        "toName": edge.get("toName"),
        "type": edge.get("type"),
        "description": edge.get("description") or "",
        "fact": edge.get("fact") or "",
        "weight": float(edge.get("weight") or 1.0),
        "kbId": edge.get("kbId"),
        "docId": edge.get("docId"),
        "evidence": [
            {
                "docId": edge.get("docId"),
                "kbId": edge.get("kbId"),
                "chunkId": edge.get("chunkId"),
                "parentId": edge.get("parentId"),
            }
        ],
    }


def update_graph_stats(
    storage: Storage, sub: str, *, delta_nodes: int, delta_edges: int, delta_docs: int
) -> dict[str, Any]:
    key = graph_stats_key(sub)

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        return {
            "nodeCount": max(0, int(data.get("nodeCount") or 0) + delta_nodes),
            "edgeCount": max(0, int(data.get("edgeCount") or 0) + delta_edges),
            "docCount": max(0, int(data.get("docCount") or 0) + delta_docs),
            "updatedAt": _now(),
        }

    return _read_modify_write(storage, key, mutate)


def upsert_graph(
    storage: Storage,
    sub: str,
    *,
    kb_id: str,
    doc_id: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge a document's entities + relationships into the user's graph.

    Expects fully resolved inputs — ``nodes`` carry ``nodeId/name/type/...`` and
    ``edges`` carry ``edgeId/from/to/fromName/toName/type/...`` (see
    ``ingestion.graph``). Idempotent when the caller deletes the document first.
    """
    tokens: list[str] = []

    def write_node(node: dict[str, Any]) -> bool:
        _, created = _merge_node(
            storage, sub, kb_id=kb_id, doc_id=doc_id, node=node
        )
        return created

    created_flags = _run_parallel(write_node, nodes)
    created_nodes = sum(1 for flag in created_flags if flag)

    # Group entity-name postings by token so a shared token is one write, not
    # one per entity that uses it.
    token_nodes: dict[str, dict[str, dict[str, Any]]] = {}
    for node in nodes:
        for token in name_tokens(node.get("name") or ""):
            token_nodes.setdefault(token, {})[str(node["nodeId"])] = node
            tokens.append(token)
    if token_nodes:
        _index_token_postings(storage, sub, token_nodes)
    if tokens:
        _update_entity_catalog(storage, sub, tokens)

    by_endpoint: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        by_endpoint.setdefault(edge["from"], []).append(
            _edge_endpoint_entry(edge, endpoint=edge["from"])
        )
        if edge["to"] != edge["from"]:
            by_endpoint.setdefault(edge["to"], []).append(
                _edge_endpoint_entry(edge, endpoint=edge["to"])
            )

    def write_endpoint(endpoint: str) -> None:
        _merge_edge_endpoints(storage, sub, endpoint, by_endpoint[endpoint])

    _run_parallel(write_endpoint, list(by_endpoint))

    unique_edge_ids = list(dict.fromkeys(edge["edgeId"] for edge in edges))
    storage.put_json(
        graph_doc_key(sub, doc_id),
        {
            "docId": doc_id,
            "kbId": kb_id,
            "userId": sub,
            "nodes": [
                {
                    "nodeId": node["nodeId"],
                    "chunkIds": list(node.get("chunkIds") or []),
                    "parentIds": list(node.get("parentIds") or []),
                }
                for node in nodes
            ],
            "edges": [
                {"id": edge["edgeId"], "from": edge["from"], "to": edge["to"]}
                for edge in edges
            ],
            "tokens": sorted(set(tokens)),
            "nodeCount": len(nodes),
            "edgeCount": len(unique_edge_ids),
            "createdAt": _now(),
        },
    )
    update_graph_stats(
        storage,
        sub,
        delta_nodes=created_nodes,
        delta_edges=len(unique_edge_ids),
        delta_docs=1,
    )
    return {
        "nodeCount": len(nodes),
        "edgeCount": len(unique_edge_ids),
        "createdNodes": created_nodes,
    }


def _unindex_node_tokens(
    storage: Storage, sub: str, tokens: list[str], node_id_: str
) -> None:
    def remove(token: str) -> None:
        key = graph_entity_term_key(sub, token)

        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            nodes = [
                entry
                for entry in (data.get("nodes") or [])
                if entry.get("nodeId") != node_id_
            ]
            return {"nodes": nodes}

        _read_modify_write(storage, key, mutate)

    _run_parallel(remove, [token for token in tokens if token])


def _remove_node_contribution(
    storage: Storage, sub: str, entry: dict[str, Any], doc_id: str
) -> bool:
    nid = str(entry.get("nodeId") or "")
    if not nid:
        return False
    key = graph_node_key(sub, nid)
    removed = {"v": False}
    chunk_drop = set(entry.get("chunkIds") or [])
    parent_drop = set(entry.get("parentIds") or [])

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        if not data:
            return data
        data["docIds"] = [d for d in (data.get("docIds") or []) if d != doc_id]
        data["chunkIds"] = [
            c for c in (data.get("chunkIds") or []) if c not in chunk_drop
        ]
        data["parentIds"] = [
            p for p in (data.get("parentIds") or []) if p not in parent_drop
        ]
        if not data["docIds"]:
            removed["v"] = True
        data["updatedAt"] = _now()
        return data

    node = _read_modify_write(storage, key, mutate)
    if not removed["v"]:
        return False
    _unindex_node_tokens(storage, sub, list(node.get("tokens") or []), nid)
    storage.delete(key)
    storage.delete(graph_adjacency_key(sub, nid))
    return True


def _remove_edge_contribution(
    storage: Storage, sub: str, endpoint_id: str, edge_id_: str, doc_id: str
) -> bool:
    if not endpoint_id:
        return False
    key = graph_adjacency_key(sub, endpoint_id)
    removed = {"v": False}

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        if not data:
            return data
        out: list[dict[str, Any]] = []
        for edge in data.get("edges") or []:
            if edge.get("id") != edge_id_:
                out.append(edge)
                continue
            evidence = [
                item
                for item in (edge.get("evidence") or [])
                if item.get("docId") != doc_id
            ]
            if not evidence:
                removed["v"] = True
                continue
            out.append({**edge, "evidence": evidence})
        data["edges"] = out
        return data

    _read_modify_write(storage, key, mutate)
    return removed["v"]


def delete_document_graph(
    storage: Storage, sub: str, doc_id: str, store: VectorStore | None = None
) -> dict[str, Any]:
    """Remove exactly what a document contributed (delete / re-index cleanup)."""
    manifest = storage.get_json(graph_doc_key(sub, doc_id))
    if not manifest:
        return {"nodesRemoved": 0, "edgesRemoved": 0}

    removed_edges: set[str] = set()
    for edge in manifest.get("edges") or []:
        edge_id_ = edge.get("id")
        if not edge_id_:
            continue
        for endpoint in {edge.get("from"), edge.get("to")}:
            if _remove_edge_contribution(storage, sub, endpoint, edge_id_, doc_id):
                removed_edges.add(edge_id_)

    # Nodes are removed after the edges: removing a node deletes its adjacency
    # object, which the edge pass above needs to see (otherwise the used edge
    # would never be counted and ``edgeCount`` would drift on every re-index).
    removed_node_ids: list[str] = []
    for entry in manifest.get("nodes") or []:
        if _remove_node_contribution(storage, sub, entry, doc_id):
            removed_node_ids.append(str(entry.get("nodeId") or ""))

    # A node that lost its last document leaves the graph, so its entity vector
    # (key ``entity:<nodeId>``) goes with it.
    if store is not None:
        vector_keys = [
            f"{ENTITY_VECTOR_KIND}:{nid}" for nid in removed_node_ids if nid
        ]
        if vector_keys:
            store.delete(sub, vector_keys)

    update_graph_stats(
        storage,
        sub,
        delta_nodes=-len(removed_node_ids),
        delta_edges=-len(removed_edges),
        delta_docs=-1,
    )
    storage.delete(graph_doc_key(sub, doc_id))
    return {"nodesRemoved": len(removed_node_ids), "edgesRemoved": len(removed_edges)}


# --- entity vectors ----------------------------------------------------------


def entity_vector_record(
    *,
    node: dict[str, Any],
    vector: list[float],
    kb_id: str,
) -> VectorRecord:
    """A vector store record for one entity (name + description embedding)."""
    nid = str(node["nodeId"])
    return VectorRecord(
        key=f"{ENTITY_VECTOR_KIND}:{nid}",
        vector=[float(value) for value in vector],
        filterable={
            "kind": ENTITY_VECTOR_KIND,
            "status": ENTITY_VECTOR_KIND,
            "nodeId": nid,
            "nodeType": str(node.get("type") or "Other"),
            "kbId": kb_id,
        },
        non_filterable={
            "text": str(node.get("name") or ""),
            "kbName": "",
            "fileName": "",
        },
    )


def entity_vector_filters(kb_ids: list[str]) -> dict[str, Any]:
    filters: dict[str, Any] = {"kind": ENTITY_VECTOR_KIND}
    if kb_ids:
        filters["kbId"] = kb_ids
    return filters


# --- traversal ---------------------------------------------------------------


def traverse(
    storage: Storage,
    sub: str,
    seeds: dict[str, float],
    *,
    kb_ids: list[str],
    hops: int,
    max_nodes: int,
    max_edges: int,
    max_fanout: int,
    decay: float,
) -> dict[str, Any]:
    """Breadth-first, score-decayed walk from seed entity nodes.

    Returns the visited nodes (with the score they were reached at and the hop
    distance) and the relationships walked. One adjacency ``GetObject`` per node
    per level, so the round trips are bounded by the node/edge caps, not the
    corpus size.
    """
    if not seeds or hops <= 0:
        return {"nodes": [], "edges": [], "visitedCount": 0}

    kb_filter = set(kb_ids) if kb_ids else None
    visited: dict[str, dict[str, Any]] = {
        nid: {"score": float(score), "hop": 0} for nid, score in seeds.items()
    }
    edges: dict[str, dict[str, Any]] = {}
    frontier = list(seeds.items())

    for hop in range(1, hops + 1):
        if not frontier or len(visited) >= max_nodes:
            break
        adjacencies = load_adjacencies(storage, sub, [nid for nid, _ in frontier])
        next_frontier: dict[str, float] = {}
        for nid, score in frontier:
            adjacency = adjacencies.get(nid)
            if not adjacency:
                continue
            taken = 0
            candidates = sorted(
                adjacency.get("edges") or [],
                key=lambda edge: -float(edge.get("weight") or 1.0),
            )
            for edge in candidates:
                if taken >= max_fanout:
                    break
                if kb_filter and edge.get("kbId") not in kb_filter:
                    continue
                neighbor = edge.get("neighbor")
                if not neighbor:
                    continue
                edges[edge.get("id") or ""] = edge
                taken += 1
                if neighbor in visited:
                    continue
                if len(visited) + len(next_frontier) >= max_nodes:
                    continue
                child_score = float(score) * decay
                if child_score > next_frontier.get(neighbor, 0.0):
                    next_frontier[neighbor] = child_score
        if len(edges) >= max_edges:
            break
        for nid, score in next_frontier.items():
            visited[nid] = {"score": score, "hop": hop}
        frontier = list(next_frontier.items())

    nodes = load_nodes(storage, sub, list(visited.keys()))
    result_nodes: list[dict[str, Any]] = []
    for nid, info in visited.items():
        node = nodes.get(nid)
        if not node:
            continue
        result_nodes.append(
            {
                "nodeId": nid,
                "name": node.get("name"),
                "type": node.get("type") or "Other",
                "description": node.get("description") or "",
                "kbIds": list(node.get("kbIds") or []),
                "docIds": list(node.get("docIds") or []),
                "chunkIds": list(node.get("chunkIds") or []),
                "parentIds": list(node.get("parentIds") or []),
                "score": info["score"],
                "hop": info["hop"],
            }
        )
    result_nodes.sort(key=lambda item: (-item["score"], item["hop"]))

    result_edges = [
        {
            "edgeId": edge_id_,
            "from": edge.get("from"),
            "to": edge.get("to"),
            "subject": edge.get("fromName"),
            "predicate": edge.get("type"),
            "object": edge.get("toName"),
            "description": edge.get("description") or edge.get("fact") or "",
            "weight": float(edge.get("weight") or 1.0),
            "kbId": edge.get("kbId"),
            "docId": edge.get("docId"),
            "chunkId": edge.get("chunkId"),
            "parentId": edge.get("parentId"),
        }
        for edge_id_, edge in edges.items()
        if edge_id_
    ]
    result_edges.sort(key=lambda item: -item["weight"])
    return {
        "nodes": result_nodes,
        "edges": result_edges[:max_edges],
        "visitedCount": len(result_nodes),
    }
