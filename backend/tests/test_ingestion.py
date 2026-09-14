"""Ingestion pipeline: extract+chunk -> embed -> index, plus the watchdog."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from support import patch_actions, patch_pipeline

from shared.dynamo.client import table
from shared.dynamo.repositories import documents, events, knowledge_bases as kb
from shared.ingestion import actions
from shared.search.hybrid import search_candidates
from shared.search.layout import raw_key
from shared.search.s3_vectors import vector_store

SUB = "auth0|pipe"
KB_ID = "kb-pipe"
DOC_ID = "doc-pipe"


def _seed(fake, monkeypatch) -> None:
    patch_actions(monkeypatch, fake)
    patch_pipeline(monkeypatch, fake)
    import shared.ingestion.pipeline as pipeline

    monkeypatch.setattr(
        pipeline,
        "embed_texts",
        lambda texts, cfg: [[float(len(text) % 3), 1.0, 0.0] for text in texts],
    )

    kb.create_kb(
        SUB,
        kb_id=KB_ID,
        name="pipe-kb",
        description="d",
        status="ready",
        embed_model="m",
        image_embed_model="im",
        embedding_dim=3,
        chunk_size=128,
        chunk_overlap=16,
    )
    key = raw_key(SUB, KB_ID, DOC_ID, "notes.md")
    doc = documents.document_item(
        doc_id=DOC_ID,
        kb_id=KB_ID,
        user_id=SUB,
        file_name="notes.md",
        s3_key=key,
        content_type="text/markdown",
        size_bytes=200,
        source="upload",
        status="uploaded",
    )
    documents.put_document(doc)
    fake.put_bytes(key, ("The personal project is a resume parser built with Python. " * 20).encode())


def test_pipeline_end_to_end(fake_storage, monkeypatch):
    _seed(fake_storage, monkeypatch)

    extracted = actions.extract_action({"documentId": DOC_ID})
    assert extracted["chunkCount"] >= 1
    assert documents.get_document_by_id(DOC_ID)["status"] == "processing"

    embedded = actions.embed_action(
        {
            "documentId": DOC_ID,
            "knowledgeBaseId": KB_ID,
            "userId": SUB,
            "chunksKey": extracted["chunksKey"],
            "images": extracted["images"],
            "config": extracted["config"],
        }
    )
    assert embedded["chunkCount"] == extracted["chunkCount"]

    indexed = actions.index_action(
        {
            "documentId": DOC_ID,
            "knowledgeBaseId": KB_ID,
            "userId": SUB,
            "chunksKey": extracted["chunksKey"],
            "embeddingsKey": embedded["embeddingsKey"],
            "images": extracted["images"],
            "config": extracted["config"],
        }
    )
    assert indexed["chunkCount"] == extracted["chunkCount"]
    assert indexed["parentCount"] >= 1

    document = documents.get_document_by_id(DOC_ID)
    assert document["status"] == "ready"
    assert kb.get_kb_by_id(KB_ID)["status"] == "ready"

    listed = events.list_events(SUB, limit=20)
    stages = [event["stage"] for event in listed]
    assert {"extracted", "chunked", "embedding", "indexed"} <= set(stages)
    # The embed stage must emit its own terminal event, otherwise the UI shows
    # "embedding" stuck in progress after indexing finishes.
    embedding = [event for event in listed if event["stage"] == "embedding"]
    assert any(event["status"] == "succeeded" for event in embedding), embedding
    # Every event must be self-describing so the events feed can associate it
    # with the document (the UI's timeline relies on this).
    assert all(
        event.get("fileName") == "notes.md" and event.get("fileKey") for event in listed
    ), listed

    hits = search_candidates(
        fake_storage,
        vector_store(fake_storage),
        SUB,
        kb_ids=[KB_ID],
        query="resume parser python",
        query_vector=[0.9, 0.1, 0.0],
        limit=5,
    )
    assert hits


def test_watchdog_reaps_stalled_documents(fake_storage, monkeypatch):
    _seed(fake_storage, monkeypatch)
    extracted = actions.extract_action({"documentId": DOC_ID})
    assert extracted  # extract sets status=processing

    # Backdate updatedAt past the threshold so the watchdog reaps it.
    item = documents.get_document_by_id(DOC_ID)
    old = (datetime.now(timezone.utc) - timedelta(minutes=120)).isoformat()
    table().update_item(
        Key={"pk": item["pk"], "sk": item["sk"]},
        UpdateExpression="SET updatedAt = :updated, gsi3sk = :gsi3sk",
        ExpressionAttributeValues={":updated": old, ":gsi3sk": f"{old}#{DOC_ID}"},
    )

    result = actions.watchdog_action({})
    assert result["reaped"] >= 1
    assert documents.get_document_by_id(DOC_ID)["status"] == "failed"
    failed = [e for e in events.list_events(SUB, limit=20) if e["stage"] == "failed"]
    assert failed and failed[0]["details"]["reason"] == "watchdog"
