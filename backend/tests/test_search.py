"""Indexing, hybrid search, tag filtering and manifest-driven cleanup."""

from __future__ import annotations

from support import patch_pipeline, patch_search

from shared.dynamo.repositories import documents, knowledge_bases as kb, tags, users
from shared.ingestion.config import load_config
from shared.ingestion.pipeline import index_document
from shared.search import service
from shared.search.hybrid import search_candidates
from shared.search.layout import (
    chunks_key,
    embeddings_key,
    manifest_key,
    parent_key,
    stats_key,
    vectors_key,
)
from shared.search.maintenance import delete_document_index
from shared.search.s3_vectors import vector_store

SUB = "auth0|search"
KB_ID = "kb-search"
DOC_ID = "doc-search"


def _stage(fake, chunks: list[dict], vectors: list[list[float]]) -> tuple[str, str]:
    chunks_path = chunks_key(SUB, KB_ID, DOC_ID)
    embeddings_path = embeddings_key(SUB, KB_ID, DOC_ID)
    parent_text = " ".join(chunk["text"] for chunk in chunks)
    fake.put_json(
        chunks_path,
        {
            "parents": [{"ordinal": 0, "page": 1, "pageEnd": 1, "text": parent_text}],
            "chunks": chunks,
        },
    )
    fake.put_json(
        embeddings_path,
        {
            "dimension": 3,
            "textModel": "m",
            "imageModel": "im",
            "chunkVectors": vectors,
            "imageVectors": [],
        },
    )
    return chunks_path, embeddings_path


def _index(fake, monkeypatch) -> None:
    patch_pipeline(monkeypatch, fake)
    chunks = [
        {
            "text": "The personal project is a resume parser built with Python.",
            "page": 1,
            "pageEnd": 1,
            "parentOrdinal": 0,
        },
        {
            "text": "It extracts skills and experience from PDF resumes.",
            "page": 1,
            "pageEnd": 1,
            "parentOrdinal": 0,
        },
    ]
    chunks_path, embeddings_path = _stage(fake, chunks, [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    index_document(
        fake,
        load_config(),
        user_id=SUB,
        knowledge_base_id=KB_ID,
        document_id=DOC_ID,
        chunks_key=chunks_path,
        embeddings_key=embeddings_path,
        images=[],
        file_name="resume.pdf",
        kb_name="my-kb",
        content_type="application/pdf",
    )


def test_index_search_delete_is_idempotent(fake_storage, monkeypatch):
    _index(fake_storage, monkeypatch)
    manifest = fake_storage.get_json(manifest_key(SUB, DOC_ID))
    assert sorted(manifest["chunkIds"]) == [f"{DOC_ID}#0", f"{DOC_ID}#1"]
    assert manifest["parentIds"] == [f"{DOC_ID}#0"]
    assert manifest["tokens"]
    parent = fake_storage.get_json(parent_key(SUB, f"{DOC_ID}#0"))
    assert parent["children"][1]["text"].startswith("It extracts")

    store = vector_store(fake_storage)
    results = search_candidates(
        fake_storage,
        store,
        SUB,
        kb_ids=[KB_ID],
        query="personal project resume",
        query_vector=[0.9, 0.1, 0.0],
        limit=10,
    )
    assert results and results[0]["chunkId"] == f"{DOC_ID}#0"
    assert results[0]["fileName"] == "resume.pdf"
    assert results[0]["kbName"] == "my-kb"
    assert results[0]["matchedContent"].startswith("The personal project")
    assert results[0]["lexicalScore"] is not None
    assert results[0]["vectorScore"] is not None

    # Re-index must not grow stats or duplicate postings.
    before = fake_storage.get_json(stats_key(SUB))
    _index(fake_storage, monkeypatch)
    assert fake_storage.get_json(stats_key(SUB)) == before

    delete_document_index(fake_storage, store, SUB, DOC_ID)
    assert fake_storage.get_json(manifest_key(SUB, DOC_ID)) is None
    assert fake_storage.get_json(parent_key(SUB, f"{DOC_ID}#0")) is None
    assert not (fake_storage.get_json(vectors_key(SUB)) or {})
    assert fake_storage.get_json(stats_key(SUB))["chunkCount"] == 0
    assert (
        search_candidates(
            fake_storage, store, SUB, kb_ids=[KB_ID], query="resume", query_vector=[1.0, 0.0, 0.0]
        )
        == []
    )


def test_service_search_and_tag_filter(fake_storage, monkeypatch):
    users.upsert_user({"sub": SUB, "https://get1agent.com/email": "search@example.com"})
    kb.create_kb(
        SUB,
        kb_id=KB_ID,
        name="my-kb",
        description="d",
        status="ready",
        embed_model="m",
        image_embed_model="im",
        embedding_dim=3,
        chunk_size=512,
        chunk_overlap=64,
    )
    doc = documents.document_item(
        doc_id=DOC_ID,
        kb_id=KB_ID,
        user_id=SUB,
        file_name="resume.pdf",
        s3_key="raw/x",
        content_type="application/pdf",
        size_bytes=10,
        source="upload",
        status="ready",
    )
    documents.put_document(doc)
    tags.replace_tags(SUB, DOC_ID, KB_ID, doc["fileKey"], [("Resume", "cv"), ("Python", "")])
    _index(fake_storage, monkeypatch)
    patch_search(monkeypatch, fake_storage)

    discovery = service.list_knowledge_bases(SUB)
    assert [item["name"] for item in discovery["knowledgeBases"]] == ["my-kb"]
    assert {t["name"] for t in discovery["knowledgeBases"][0]["tags"]} == {"Resume", "Python"}

    matched = service.search(SUB, "personal project resume", [0.9, 0.1, 0.0], tags=["Resume"])
    assert matched["candidates"]
    assert matched["candidates"][0]["documentId"] == DOC_ID
    assert matched["knowledgeBases"][0]["name"] == "my-kb"

    filtered = service.search(SUB, "personal project resume", [0.9, 0.1, 0.0], tags=["Nope"])
    assert filtered["candidates"] == []

    unknown = service.search(SUB, "resume", [1.0, 0.0, 0.0], knowledge_base_names=["missing"])
    assert unknown["candidates"] == []
    assert unknown["warnings"] and "Unknown knowledge bases" in unknown["warnings"][0]
