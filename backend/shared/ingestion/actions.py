from __future__ import annotations

from typing import Any

from shared.ingestion.pipeline import (
    emit_event,
    extract_document,
    get_document,
    index_document,
    load_config_for_knowledge_base,
    set_document_status,
)
from shared.storage import Storage


class DocumentNotReady(Exception):
    """S3 delivered the event before the upload was marked complete."""


class DocumentMissing(Exception):
    """No document row matches the S3 object."""


def _storage() -> Storage:
    return Storage()


def _error_message(error: dict[str, Any] | None) -> str:
    if not error:
        return "Ingestion failed"
    cause = error.get("Cause")
    if isinstance(cause, str) and cause:
        return cause
    return str(error.get("Error") or "Ingestion failed")


async def extract_action(event: dict[str, Any]) -> dict[str, Any]:
    """Stage 1: download, parse text + images, and stage derived artifacts."""
    document = await get_document(event["documentId"])
    if document is None:
        raise DocumentMissing(f"Document {event['documentId']} not found")
    if document["status"] == "pending":
        raise DocumentNotReady(f"Document {event['documentId']} is not uploaded yet")

    config = await load_config_for_knowledge_base(document["knowledge_base_id"])
    await set_document_status(document["id"], "processing")
    await emit_event(
        document_id=document["id"],
        knowledge_base_id=document["knowledge_base_id"],
        user_id=document["user_id"],
        stage="extracted",
        status="started",
        message=document["file_name"],
    )
    extracted = extract_document(
        _storage(),
        config,
        user_id=document["user_id"],
        knowledge_base_id=document["knowledge_base_id"],
        document_id=document["id"],
        s3_key=document["s3_key"],
        file_name=document["file_name"],
    )
    await emit_event(
        document_id=document["id"],
        knowledge_base_id=document["knowledge_base_id"],
        user_id=document["user_id"],
        stage="extracted",
        status="succeeded",
        message=f"{extracted.image_count} image{'s' if extracted.image_count != 1 else ''}",
    )
    return {
        "documentId": document["id"],
        "knowledgeBaseId": document["knowledge_base_id"],
        "userId": document["user_id"],
        "textKey": extracted.text_key,
        "images": extracted.images,
        "imageCount": extracted.image_count,
    }


async def index_action(event: dict[str, Any]) -> dict[str, Any]:
    """Stage 2: chunk + embed text/images and persist vectors."""
    config = await load_config_for_knowledge_base(event["knowledgeBaseId"])
    indexed = await index_document(
        _storage(),
        config,
        user_id=event["userId"],
        knowledge_base_id=event["knowledgeBaseId"],
        document_id=event["documentId"],
        text_key=event["textKey"],
        images=event.get("images") or [],
    )
    await set_document_status(
        event["documentId"],
        "ready",
        chunk_count=indexed.chunk_count,
        image_count=indexed.image_count,
        embed_model=config.text_embed_model,
        image_embed_model=config.image_embed_model if indexed.image_count else None,
    )
    await emit_event(
        document_id=event["documentId"],
        knowledge_base_id=event["knowledgeBaseId"],
        user_id=event["userId"],
        stage="indexed",
        status="succeeded",
        message=(
            f"{indexed.chunk_count} chunk{'s' if indexed.chunk_count != 1 else ''} · "
            f"{indexed.image_count} image{'s' if indexed.image_count != 1 else ''} indexed"
        ),
    )
    return {"chunkCount": indexed.chunk_count, "imageCount": indexed.image_count}


async def mark_failed_action(event: dict[str, Any]) -> dict[str, Any]:
    """Failure handler: mark the document failed and record the failed stage."""
    failed_stage = event.get("stage") or "unknown"
    message = _error_message(event.get("error"))
    await set_document_status(event["documentId"], "failed")
    await emit_event(
        document_id=event["documentId"],
        knowledge_base_id=event["knowledgeBaseId"],
        user_id=event["userId"],
        stage="failed",
        status="failed",
        message=f"{failed_stage}: {message}",
        details={"failedStage": failed_stage},
    )
    return {"ok": True}
