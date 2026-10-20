"""Graph RAG: graph ingest, the S3 graph store/traversal, retrieval augmentation.

The graph is plain S3 JSON (no external graph database), so every layer is
exercised against the in-memory storage double:

* ``retrieval.graph`` — the store: upsert, traversal, idempotent per-document
  delete.
* ``ingestion.graph`` — extraction: chunks → typed entities/relationships +
  entity vectors (the model call is stubbed).
* ``src.search.graph`` — query time: seed → traverse → resolve to parents
  (the graph's own retrieval path; the hybrid legs are only its fallback).
* ``ingestion.actions.graph_extract_action`` — the gated, best-effort stage.
"""

from __future__ import annotations

from support import patch_actions, patch_pipeline, patch_search

from data.repositories import documents, knowledge_bases as kb, users
from retrieval import graph as graph_store
from retrieval.embedding.config import config_to_dict, load_config
from retrieval.layout import chunks_key, embeddings_key, parent_key
from retrieval.s3_vectors import vector_store
from ingestion.pipeline import index_document
from src.search import service
from src.search import graph as graph_retrieval

SUB = "auth0|graph"
KB_ID = "kb-graph"
DOC_A = "doc-a"
DOC_B = "doc-b"
DOC_C = "doc-c"
KB_H = "kb-hybrid"
DIM = 3


def _user_id() -> str:
    return users.upsert_user(
        {"sub": SUB, "https://get1agent.com/email": "graph@example.com"}
    )["userId"]


def _parent_doc(
    fake,
    user_id: str,
    *,
    doc_id: str,
    parent_id: str,
    page: int,
    text: str,
    children: list[tuple[str, str]],
) -> None:
    fake.put_json(
        parent_key(user_id, parent_id),
        {
            "parentId": parent_id,
            "docId": doc_id,
            "kbId": KB_ID,
            "userId": user_id,
            "fileName": f"{doc_id}.pdf",
            "kbName": "graph-kb",
            "contentType": "application/pdf",
            "ordinal": 0,
            "page": page,
            "pageEnd": page,
            "content": text,
            "tokenCount": max(1, len(text) // 4),
            "children": [
                {
                    "chunkId": chunk_id,
                    "ordinal": index,
                    "text": child_text,
                    "page": page,
                    "pageEnd": page,
                    "tokenCount": max(1, len(child_text) // 4),
                }
                for index, (chunk_id, child_text) in enumerate(children)
            ],
        },
    )


def _upsert_two_docs(fake, user_id: str) -> dict:
    """A two-document graph that shares one entity (Beta Labs).

    Alice -WORKS_AT-> Acme Corp   (doc A)
    Acme Corp -PARTNERS_WITH-> Beta Labs   (doc A)
    Beta Labs -PRODUCES-> Gamma Project   (doc B)
    """
    alice = {
        "nodeId": graph_store.node_id("Alice", "Person"),
        "name": "Alice",
        "type": "Person",
        "description": "An engineer.",
        "chunkIds": [f"{DOC_A}#0"],
        "parentIds": [f"{DOC_A}#0"],
    }
    acme = {
        "nodeId": graph_store.node_id("Acme Corp", "Organization"),
        "name": "Acme Corp",
        "type": "Organization",
        "description": "A company.",
        "chunkIds": [f"{DOC_A}#0"],
        "parentIds": [f"{DOC_A}#0"],
    }
    beta = {
        "nodeId": graph_store.node_id("Beta Labs", "Organization"),
        "name": "Beta Labs",
        "type": "Organization",
        "description": "A partner.",
        "chunkIds": [f"{DOC_A}#0", f"{DOC_B}#0"],
        "parentIds": [f"{DOC_A}#0", f"{DOC_B}#0"],
    }
    gamma = {
        "nodeId": graph_store.node_id("Gamma Project", "Product"),
        "name": "Gamma Project",
        "type": "Product",
        "description": "A product.",
        "chunkIds": [f"{DOC_B}#0"],
        "parentIds": [f"{DOC_B}#0"],
    }

    def edge(source: dict, rel: str, target: dict, doc_id: str, chunk_id: str) -> dict:
        return {
            "edgeId": graph_store.edge_id(source["nodeId"], rel, target["nodeId"]),
            "from": source["nodeId"],
            "to": target["nodeId"],
            "fromName": source["name"],
            "toName": target["name"],
            "fromType": source["type"],
            "toType": target["type"],
            "type": rel,
            "description": f"{source['name']} {rel.lower()} {target['name']}",
            "fact": f"{source['name']} {rel.lower()} {target['name']}",
            "weight": 1.0,
            "kbId": KB_ID,
            "docId": doc_id,
            "chunkId": chunk_id,
            "parentId": f"{doc_id}#0",
        }

    graph_store.upsert_graph(
        fake,
        user_id,
        kb_id=KB_ID,
        doc_id=DOC_A,
        nodes=[alice, acme, beta],
        edges=[
            edge(alice, "WORKS_AT", acme, DOC_A, f"{DOC_A}#0"),
            edge(acme, "PARTNERS_WITH", beta, DOC_A, f"{DOC_A}#0"),
        ],
    )
    graph_store.upsert_graph(
        fake,
        user_id,
        kb_id=KB_ID,
        doc_id=DOC_B,
        nodes=[beta, gamma],
        edges=[edge(beta, "PRODUCES", gamma, DOC_B, f"{DOC_B}#0")],
    )
    return {"alice": alice, "acme": acme, "beta": beta, "gamma": gamma}


def _stage_and_index(
    fake,
    monkeypatch,
    user_id: str,
    *,
    doc_id: str,
    text_a: str,
    text_b: str,
    vector_a: list[float],
    vector_b: list[float],
    kb_id: str = KB_ID,
    kb_name: str = "graph-kb",
) -> None:
    chunks_path = chunks_key(user_id, kb_id, doc_id)
    embeddings_path = embeddings_key(user_id, kb_id, doc_id)
    fake.put_json(
        chunks_path,
        {
            "parents": [
                {"ordinal": 0, "page": 1, "pageEnd": 1, "text": f"{text_a} {text_b}"}
            ],
            "chunks": [
                {"text": text_a, "page": 1, "pageEnd": 1, "parentOrdinal": 0},
                {"text": text_b, "page": 1, "pageEnd": 1, "parentOrdinal": 0},
            ],
        },
    )
    fake.put_json(
        embeddings_path,
        {
            "dimension": DIM,
            "textModel": "m",
            "imageModel": "im",
            "chunkVectors": [vector_a, vector_b],
            "imageVectors": [],
        },
    )
    patch_pipeline(monkeypatch, fake)
    index_document(
        fake,
        load_config(),
        user_id=user_id,
        knowledge_base_id=kb_id,
        document_id=doc_id,
        chunks_key=chunks_path,
        embeddings_key=embeddings_path,
        images=[],
        file_name=f"{doc_id}.pdf",
        kb_name=kb_name,
        content_type="application/pdf",
    )


# --- store + traversal -------------------------------------------------------


def test_traverse_multi_hop_and_idempotent_delete(fake_storage):
    user_id = _user_id()
    nodes = _upsert_two_docs(fake_storage, user_id)

    stats = graph_store.read_stats(fake_storage, user_id)
    assert stats["nodeCount"] == 4  # Alice, Acme, Beta (created once), Gamma
    assert stats["edgeCount"] == 3
    assert stats["docCount"] == 2
    assert graph_store.graph_exists(fake_storage, user_id) is True

    walked = graph_store.traverse(
        fake_storage,
        user_id,
        {nodes["alice"]["nodeId"]: 1.0},
        kb_ids=[KB_ID],
        hops=2,
        max_nodes=60,
        max_edges=120,
        max_fanout=24,
        decay=0.7,
    )
    reached = {node["nodeId"] for node in walked["nodes"]}
    # hop 1 = Acme, hop 2 = Beta (reached through the Acme→Beta edge).
    assert reached == {
        nodes["alice"]["nodeId"],
        nodes["acme"]["nodeId"],
        nodes["beta"]["nodeId"],
    }
    hop_of = {node["nodeId"]: node["hop"] for node in walked["nodes"]}
    assert hop_of[nodes["beta"]["nodeId"]] == 2
    assert walked["nodes"][0]["nodeId"] == nodes["alice"]["nodeId"]  # seed scores highest
    assert {edge["predicate"] for edge in walked["edges"]} == {
        "WORKS_AT",
        "PARTNERS_WITH",
    }

    # Deleting doc A drops the nodes only it contributed, keeps the shared one.
    removed = graph_store.delete_document_graph(fake_storage, user_id, DOC_A)
    assert removed["nodesRemoved"] == 2  # Alice + Acme
    assert removed["edgesRemoved"] == 2  # WORKS_AT + PARTNERS_WITH
    assert graph_store.read_node(fake_storage, user_id, nodes["alice"]["nodeId"]) is None
    beta = graph_store.read_node(fake_storage, user_id, nodes["beta"]["nodeId"])
    assert beta is not None and beta["docIds"] == [DOC_B]
    stats = graph_store.read_stats(fake_storage, user_id)
    assert stats["nodeCount"] == 2  # Beta + Gamma
    assert stats["edgeCount"] == 1  # PRODUCES
    assert stats["docCount"] == 1


def test_kb_filter_excludes_other_knowledge_bases(fake_storage):
    user_id = _user_id()
    nodes = _upsert_two_docs(fake_storage, user_id)
    walked = graph_store.traverse(
        fake_storage,
        user_id,
        {nodes["beta"]["nodeId"]: 1.0},
        kb_ids=["some-other-kb"],
        hops=1,
        max_nodes=60,
        max_edges=120,
        max_fanout=24,
        decay=0.7,
    )
    # The only reachable node is the seed itself; its edges belong to KB_ID.
    assert {node["nodeId"] for node in walked["nodes"]} == {nodes["beta"]["nodeId"]}
    assert walked["edges"] == []


# --- query-time augmentation -------------------------------------------------


def test_search_graph_resolves_parents_and_merges(fake_storage):
    user_id = _user_id()
    nodes = _upsert_two_docs(fake_storage, user_id)
    _parent_doc(
        fake_storage,
        user_id,
        doc_id=DOC_A,
        parent_id=f"{DOC_A}#0",
        page=1,
        text="Alice works at Acme Corp, which partners with Beta Labs.",
        children=[(f"{DOC_A}#0", "Alice works at Acme Corp.")],
    )
    _parent_doc(
        fake_storage,
        user_id,
        doc_id=DOC_B,
        parent_id=f"{DOC_B}#0",
        page=2,
        text="Beta Labs produces the Gamma Project.",
        children=[(f"{DOC_B}#0", "Beta Labs produces Gamma Project.")],
    )

    store = vector_store(fake_storage)
    result = graph_retrieval.search_graph(
        fake_storage,
        store,
        user_id,
        query="alice acme",
        query_vector=[0.1, 0.2, 0.3],
        kb_ids=[KB_ID],
    )
    parents = {candidate["parentId"] for candidate in result["candidates"]}
    assert parents == {f"{DOC_A}#0", f"{DOC_B}#0"}
    assert result["meta"]["enabled"] is True
    assert result["meta"]["nodes"] >= 3
    predicates = {rel["predicate"] for rel in result["relationships"]}
    assert {"WORKS_AT", "PARTNERS_WITH"} <= predicates

    # The best-scoring node annotates each parent.
    by_parent = {candidate["parentId"]: candidate for candidate in result["candidates"]}
    assert by_parent[f"{DOC_A}#0"]["graphNode"] in {"Acme Corp", "Alice"}
    assert by_parent[f"{DOC_A}#0"]["source"] == "graph"


# --- extraction --------------------------------------------------------------


def _fake_extract(bundle: str, *, model: str, max_tokens: int) -> dict:
    return {
        "entities": [
            {"name": "Acme Corp", "type": "Organization", "description": "A company."},
            {"name": "Alice", "type": "Person", "description": "An engineer."},
        ],
        "relationships": [
            {
                "source": "Alice",
                "target": "Acme Corp",
                "type": "WORKS_AT",
                "description": "Alice works at Acme.",
                "weight": 1.0,
            }
        ],
    }


def test_build_graph_extracts_embeds_and_is_idempotent(fake_storage, monkeypatch):
    import ingestion.graph as ingestion_graph

    user_id = _user_id()
    chunks_path = chunks_key(user_id, KB_ID, DOC_A)
    fake_storage.put_json(
        chunks_path,
        {
            "parents": [
                {"ordinal": 0, "page": 1, "pageEnd": 1, "text": "Alice works at Acme Corp."}
            ],
            "chunks": [
                {
                    "text": "Alice works at Acme Corp.",
                    "page": 1,
                    "pageEnd": 1,
                    "parentOrdinal": 0,
                }
            ],
        },
    )
    monkeypatch.setattr(ingestion_graph, "_extract_batch", _fake_extract)
    monkeypatch.setattr(
        ingestion_graph,
        "embed_texts",
        lambda texts, config: [[0.5, 0.25, 0.25] for _ in texts],
    )

    summary = ingestion_graph.build_graph(
        fake_storage,
        load_config(),
        user_id=user_id,
        knowledge_base_id=KB_ID,
        document_id=DOC_A,
        chunks_key=chunks_path,
    )
    assert summary == {"entities": 2, "relationships": 1, "batches": 1, "failedBatches": 0}

    alice_id = graph_store.node_id("Alice", "Person")
    alice = graph_store.read_node(fake_storage, user_id, alice_id)
    assert alice is not None
    assert alice["type"] == "Person"
    assert alice["parentIds"] == [f"{DOC_A}#0"]
    assert alice["chunkIds"] == [f"{DOC_A}#0"]

    store = vector_store(fake_storage)
    entity_hits = store.query(
        user_id, [0.5, 0.25, 0.25], 5, filters={"kind": "entity"}
    )
    assert len(entity_hits) == 2
    # Entity vectors must never surface in a chunk search (which filters ready).
    assert store.query(user_id, [0.5, 0.25, 0.25], 5, filters={"status": "ready"}) == []

    before = graph_store.read_stats(fake_storage, user_id)
    assert before["nodeCount"] == 2
    assert before["edgeCount"] == 1

    # Re-running the same document (re-index/retry) must not grow the graph.
    ingestion_graph.build_graph(
        fake_storage,
        load_config(),
        user_id=user_id,
        knowledge_base_id=KB_ID,
        document_id=DOC_A,
        chunks_key=chunks_path,
    )
    after = graph_store.read_stats(fake_storage, user_id)
    assert (after["nodeCount"], after["edgeCount"], after["docCount"]) == (
        before["nodeCount"],
        before["edgeCount"],
        before["docCount"],
    )


def test_build_graph_batch_failure_is_counted_not_raised(fake_storage, monkeypatch):
    import ingestion.graph as ingestion_graph

    user_id = _user_id()
    chunks_path = chunks_key(user_id, KB_ID, DOC_A)
    fake_storage.put_json(
        chunks_path,
        {
            "parents": [{"ordinal": 0, "page": 1, "pageEnd": 1, "text": "t"}],
            "chunks": [
                {"text": "one", "page": 1, "pageEnd": 1, "parentOrdinal": 0},
                {"text": "two", "page": 1, "pageEnd": 1, "parentOrdinal": 0},
            ],
        },
    )

    def boom(bundle: str, *, model: str, max_tokens: int) -> dict:
        raise RuntimeError("model throttled")

    monkeypatch.setattr(ingestion_graph, "_extract_batch", boom)
    monkeypatch.setenv("GRAPH_EXTRACT_BATCH_CHUNKS", "1")
    monkeypatch.setattr(
        ingestion_graph, "embed_texts", lambda texts, config: [[0.1] * DIM for _ in texts]
    )

    summary = ingestion_graph.build_graph(
        fake_storage,
        load_config(),
        user_id=user_id,
        knowledge_base_id=KB_ID,
        document_id=DOC_A,
        chunks_key=chunks_path,
    )
    assert summary["batches"] == 2
    assert summary["failedBatches"] == 2
    assert summary["entities"] == 0
    assert graph_store.read_stats(fake_storage, user_id)["nodeCount"] == 0


# --- the stage -----------------------------------------------------------------


def test_graph_extract_action_skips_hybrid_mode(fake_storage, monkeypatch):
    import ingestion.actions as actions

    user_id = _user_id()
    patch_actions(monkeypatch, fake_storage)
    result = actions.graph_extract_action(
        {
            "documentId": DOC_A,
            "knowledgeBaseId": KB_ID,
            "userId": user_id,
            "chunksKey": chunks_key(user_id, KB_ID, DOC_A),
            "config": config_to_dict(load_config()),  # retrieval_mode defaults to hybrid
        }
    )
    assert result == {"skipped": True, "reason": "hybrid mode"}


def test_graph_extract_action_runs_for_graph_mode(fake_storage, monkeypatch):
    import ingestion.actions as actions
    import ingestion.graph as ingestion_graph
    from data.repositories import events as events_repo

    user_id = _user_id()
    patch_actions(monkeypatch, fake_storage)
    chunks_path = chunks_key(user_id, KB_ID, DOC_A)
    fake_storage.put_json(
        chunks_path,
        {
            "parents": [
                {"ordinal": 0, "page": 1, "pageEnd": 1, "text": "Alice works at Acme Corp."}
            ],
            "chunks": [
                {
                    "text": "Alice works at Acme Corp.",
                    "page": 1,
                    "pageEnd": 1,
                    "parentOrdinal": 0,
                }
            ],
        },
    )
    monkeypatch.setattr(ingestion_graph, "_extract_batch", _fake_extract)
    monkeypatch.setattr(
        ingestion_graph, "embed_texts", lambda texts, config: [[0.5, 0.25, 0.25] for _ in texts]
    )

    config = dict(config_to_dict(load_config()))
    config["retrieval_mode"] = "graph"
    result = actions.graph_extract_action(
        {
            "documentId": DOC_A,
            "knowledgeBaseId": KB_ID,
            "userId": user_id,
            "chunksKey": chunks_path,
            "config": config,
        }
    )
    assert result["entities"] == 2
    assert result["relationships"] == 1
    assert graph_store.read_stats(fake_storage, user_id)["nodeCount"] == 2

    events = events_repo.list_events(user_id)
    graph_events = [event for event in events if event["stage"] == "graph"]
    assert {event["status"] for event in graph_events} == {"started", "succeeded"}


def test_state_machine_gate_reads_the_actual_payload_key():
    """The GraphMode Choice must read the key ``extract_action`` emits.

    ``extract_action`` returns ``config_to_dict(config)`` (snake_case), so a
    camelCase ``$.extracted.config.retrievalMode`` path never matches and every
    Graph knowledge base silently skips the graph stage. Pinning the ASL to the
    payload key keeps the gate honest.
    """
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    asl = json.loads(
        (root / "infra/terraform/modules/ingestion/statemachine.asl.json").read_text()
    )
    choices = asl["States"]["GraphMode"]["Choices"][0]["And"]
    assert {choice["Variable"] for choice in choices} == {
        "$.extracted.config.retrieval_mode"
    }
    # GraphMode runs after Index, so Index must merge into the state instead of
    # replacing it — otherwise `extracted` is gone by the time the Choice runs.
    assert asl["States"]["Index"].get("ResultPath") == "$.indexed"
    assert "retrieval_mode" in config_to_dict(load_config())


# --- end to end through the search service -----------------------------------


def test_service_search_augments_graph_kb(fake_storage, monkeypatch):
    user_id = _user_id()
    kb.create_kb(
        user_id,
        kb_id=KB_ID,
        name="graph-kb",
        description="d",
        status="ready",
        embed_model="m",
        image_embed_model="im",
        embedding_dim=DIM,
        chunk_size=512,
        chunk_overlap=64,
        retrieval_mode="graph",
    )
    doc = documents.document_item(
        doc_id=DOC_A,
        kb_id=KB_ID,
        user_id=user_id,
        file_name="doc-a.pdf",
        s3_key="raw/x",
        content_type="application/pdf",
        size_bytes=10,
        source="upload",
        status="ready",
    )
    documents.put_document(doc)

    _stage_and_index(
        fake_storage,
        monkeypatch,
        user_id,
        doc_id=DOC_A,
        text_a="Alice works at Acme Corp.",
        text_b="Acme Corp partners with Beta Labs.",
        vector_a=[1.0, 0.0, 0.0],
        vector_b=[0.0, 1.0, 0.0],
    )
    # A graph-only document: its parent has no chunk vectors, so it can only be
    # reached through the graph (this is the widening Graph RAG adds).
    nodes = _upsert_two_docs(fake_storage, user_id)
    _parent_doc(
        fake_storage,
        user_id,
        doc_id=DOC_A,
        parent_id=f"{DOC_A}#0",
        page=1,
        text="Alice works at Acme Corp. Acme Corp partners with Beta Labs.",
        children=[
            (f"{DOC_A}#0", "Alice works at Acme Corp."),
            (f"{DOC_A}#1", "Acme Corp partners with Beta Labs."),
        ],
    )
    _parent_doc(
        fake_storage,
        user_id,
        doc_id=DOC_B,
        parent_id=f"{DOC_B}#0",
        page=2,
        text="Beta Labs produces the Gamma Project.",
        children=[(f"{DOC_B}#0", "Beta Labs produces Gamma Project.")],
    )
    patch_search(monkeypatch, fake_storage)

    # A Graph-mode knowledge base answers graph-first: the graph is its own
    # retrieval path, not an annotation on the hybrid list.
    result = service.search(user_id, "alice acme corp", [1.0, 0.0, 0.0], limit=10)
    assert result["knowledgeBases"][0]["retrievalMode"] == "graph"
    assert result["graph"]["enabled"] is True
    assert result["graph"]["strategy"] == "graph"
    assert result["graph"]["fallback"] is False
    parents = {candidate["parentId"] for candidate in result["candidates"]}
    assert f"{DOC_B}#0" in parents  # graph-only widening
    assert result["relationships"]
    for candidate in result["candidates"]:
        assert candidate["source"] == "graph"

    # The graph finds nothing for this query: the hybrid legs answer it instead
    # and the payload says so, rather than silently looking like a graph result.
    empty_graph = {
        "candidates": [],
        "relationships": [],
        "meta": {"enabled": True, "seeds": 0, "nodes": 0, "edges": 0, "relations": 0},
    }
    real_search_graph = graph_retrieval.search_graph
    monkeypatch.setattr(
        graph_retrieval, "search_graph", lambda *args, **kwargs: empty_graph
    )
    fallback = service.search(user_id, "alice acme corp", [1.0, 0.0, 0.0])
    assert fallback["graph"]["fallback"] is True
    assert fallback["graph"]["reason"] == "no matching entities"
    assert fallback["relationships"] == []
    assert {candidate["parentId"] for candidate in fallback["candidates"]} == {
        f"{DOC_A}#0"
    }

    # An explicit opt-out forces the hybrid path even on a Graph KB.
    plain = service.search(user_id, "alice acme corp", [1.0, 0.0, 0.0], graph=False)
    assert plain["graph"]["enabled"] is False
    assert plain["graph"]["strategy"] == "hybrid"
    assert plain["graph"]["fallback"] is False
    assert plain["graph"]["reason"] == "graph not requested"
    assert plain["relationships"] == []
    assert {candidate["parentId"] for candidate in plain["candidates"]} == {f"{DOC_A}#0"}

    monkeypatch.setattr(graph_retrieval, "search_graph", real_search_graph)

    # A mixed selection searches each knowledge base its own way: the graph
    # answers the Graph KB, the hybrid legs answer the Hybrid KB, and both are
    # represented — neither strategy is fused into the other.
    kb.create_kb(
        user_id,
        kb_id=KB_H,
        name="hybrid-kb",
        description="d",
        status="ready",
        embed_model="m",
        image_embed_model="im",
        embedding_dim=DIM,
        chunk_size=512,
        chunk_overlap=64,
        retrieval_mode="hybrid",
    )
    documents.put_document(
        documents.document_item(
            doc_id=DOC_C,
            kb_id=KB_H,
            user_id=user_id,
            file_name="doc-c.pdf",
            s3_key="raw/y",
            content_type="application/pdf",
            size_bytes=10,
            source="upload",
            status="ready",
        )
    )
    _stage_and_index(
        fake_storage,
        monkeypatch,
        user_id,
        doc_id=DOC_C,
        text_a="Alice works at Acme Corp.",
        text_b="Acme Corp partners with Beta Labs.",
        vector_a=[1.0, 0.0, 0.0],
        vector_b=[0.0, 1.0, 0.0],
        kb_id=KB_H,
        kb_name="hybrid-kb",
    )
    mixed = service.search(
        user_id,
        "alice acme corp",
        [1.0, 0.0, 0.0],
        knowledge_base_names=["graph-kb", "hybrid-kb"],
        limit=10,
    )
    assert mixed["graph"]["fallback"] is False
    assert {candidate["source"] for candidate in mixed["candidates"]} == {"graph", "hybrid"}
    assert {candidate["knowledgeBaseId"] for candidate in mixed["candidates"]} == {
        KB_ID,
        KB_H,
    }
    # Interleaved, so a long graph list cannot bury the hybrid results.
    assert [candidate["source"] for candidate in mixed["candidates"][:2]] == [
        "graph",
        "hybrid",
    ]


def test_extract_batch_disables_model_reasoning(monkeypatch):
    import ingestion.graph as ingestion_graph

    captured: dict = {}

    def fake_chat_result(system, user, **kwargs):
        captured.update(kwargs)
        return {
            "structured": {"entities": [], "relationships": []},
            "stopReason": "end_turn",
            "usage": {},
        }

    monkeypatch.setattr(ingestion_graph.bedrock_chat, "chat_result", fake_chat_result)
    ingestion_graph._extract_batch("excerpt", model="m", max_tokens=100)
    # A reasoning model left on spends the whole budget thinking and returns no
    # JSON; extraction turns it off.
    assert captured["extra_fields"] == {"thinking": {"type": "disabled"}}


def test_extract_or_split_halves_a_truncated_batch(monkeypatch):
    import ingestion.graph as ingestion_graph

    calls: list[str] = []

    def fake_extract(bundle, *, model, max_tokens):
        calls.append(bundle)
        if "alpha" in bundle and "beta" in bundle:
            raise ingestion_graph.GraphExtractionError(
                "model returned no usable JSON "
                "(stopReason=max_tokens, outputTokens=100)"
            )
        return {"entities": [], "relationships": []}

    monkeypatch.setattr(ingestion_graph, "_extract_batch", fake_extract)
    records = [{"text": "alpha", "page": 1}, {"text": "beta", "page": 1}]
    parts = ingestion_graph._extract_or_split(records, model="m", max_tokens=100)
    assert len(calls) == 3  # combined batch truncates, then each half succeeds
    assert [part[1] for part in parts] == [[records[0]], [records[1]]]

