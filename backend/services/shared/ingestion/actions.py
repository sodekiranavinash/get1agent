from __future__ import annotations

import os
from typing import Any

from shared.ingestion.config import config_from_dict, config_to_dict, load_config
from shared.ingestion.pipeline import (
    embed_document,
    emit_event,
    extract_document,
    find_stalled_documents,
    get_document,
    index_document,
    load_config_for_knowledge_base,
    set_document_status,
)
from shared.observability import get_logger
from shared.storage import Storage

logger = get_logger("ingestion")


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


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _extract_message(stats: dict[str, int]) -> str:
    parts: list[str] = []
    source_bytes = stats.get("sourceBytes")
    if source_bytes:
        parts.append(_format_bytes(source_bytes))
    images = stats.get("images")
    if images:
        parts.append(f"{images:,} image{'s' if images != 1 else ''}")
    for key, label in (("pages", "page"), ("sheets", "sheet"), ("rows", "row")):
        value = stats.get(key)
        if value:
            parts.append(f"{value:,} {label}{'s' if value != 1 else ''}")
    words = stats.get("words")
    if words:
        parts.append(f"{words:,} word{'s' if words != 1 else ''}")
    return " · ".join(parts) or "Parsed"


def extract_action(event: dict[str, Any]) -> dict[str, Any]:
    """Stage 1: download, parse text + images, chunk, and stage derived artifacts."""
    document = get_document(event["documentId"])
    if document is None:
        raise DocumentMissing(f"Document {event['documentId']} not found")
    if document["status"] == "pending":
        raise DocumentNotReady(f"Document {event['documentId']} is not uploaded yet")

    logger.info(
        "extract started",
        extra={
            "documentId": document["id"],
            "knowledgeBaseId": document["knowledge_base_id"],
            "stage": "extracted",
        },
    )

    config = load_config_for_knowledge_base(document["knowledge_base_id"])
    set_document_status(document["id"], "processing")
    emit_event(
        document_id=document["id"],
        knowledge_base_id=document["knowledge_base_id"],
        user_id=document["user_id"],
        stage="extracted",
        status="started",
        message=document["file_name"],
        file_name=document["file_name"],
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
    emit_event(
        document_id=document["id"],
        knowledge_base_id=document["knowledge_base_id"],
        user_id=document["user_id"],
        stage="extracted",
        status="succeeded",
        message=_extract_message(extracted.stats),
        details=extracted.stats,
        file_name=document["file_name"],
    )
    emit_event(
        document_id=document["id"],
        knowledge_base_id=document["knowledge_base_id"],
        user_id=document["user_id"],
        stage="chunked",
        status="succeeded",
        message=(
            f"{extracted.chunk_count} chunk"
            f"{'s' if extracted.chunk_count != 1 else ''} "
            f"· {config.chunk_size}/{config.chunk_overlap}"
            + (
                f" · {extracted.parent_count} page/window"
                f"{'s' if extracted.parent_count != 1 else ''}"
                if extracted.parent_count
                else ""
            )
        ),
        details=extracted.chunk_stats,
        file_name=document["file_name"],
    )
    emit_event(
        document_id=document["id"],
        knowledge_base_id=document["knowledge_base_id"],
        user_id=document["user_id"],
        stage="embedding",
        status="started",
        message=(
            f"Embedding {extracted.chunk_count} text chunk"
            f"{'s' if extracted.chunk_count != 1 else ''}"
            + (
                f" + {extracted.image_count} image"
                f"{'s' if extracted.image_count != 1 else ''}"
                if extracted.images
                else ""
            )
        ),
        details={
            "textEmbeddings": extracted.chunk_count,
            "imageEmbeddings": extracted.image_count,
            "dimension": config.embedding_dim,
        },
        file_name=document["file_name"],
    )
    logger.info(
        "extract succeeded",
        extra={
            "documentId": document["id"],
            "knowledgeBaseId": document["knowledge_base_id"],
            "stage": "extracted",
        },
    )
    return {
        "documentId": document["id"],
        "knowledgeBaseId": document["knowledge_base_id"],
        "userId": document["user_id"],
        "chunksKey": extracted.chunks_key,
        "images": extracted.images,
        "imageCount": extracted.image_count,
        "chunkCount": extracted.chunk_count,
        "config": config_to_dict(config),
    }


def embed_action(event: dict[str, Any]) -> dict[str, Any]:
    """Stage 2: compute embeddings (S3 + Bedrock/Ollama only)."""
    config = config_from_dict(load_config(), event.get("config"))
    logger.info(
        "embed started",
        extra={
            "documentId": event["documentId"],
            "knowledgeBaseId": event["knowledgeBaseId"],
            "stage": "embedding",
        },
    )
    embedded = embed_document(
        _storage(),
        config,
        chunks_key=event["chunksKey"],
        images=event.get("images") or [],
    )
    total = embedded.chunk_count + embedded.image_count
    emit_event(
        document_id=event["documentId"],
        knowledge_base_id=event["knowledgeBaseId"],
        user_id=event["userId"],
        stage="embedding",
        status="succeeded",
        message=(
            f"{embedded.chunk_count} text"
            + (f" · {embedded.image_count} image" if embedded.image_count else "")
            + f" embedding{'s' if total != 1 else ''}"
        ),
        details={
            "textEmbeddings": embedded.chunk_count,
            "imageEmbeddings": embedded.image_count,
            "dimension": embedded.dimension,
            "model": embedded.text_model,
        },
    )
    logger.info(
        "embed succeeded",
        extra={
            "documentId": event["documentId"],
            "knowledgeBaseId": event["knowledgeBaseId"],
            "stage": "embedding",
        },
    )
    return {
        "embeddingsKey": embedded.embeddings_key,
        "chunkCount": embedded.chunk_count,
        "imageCount": embedded.image_count,
        "dimension": embedded.dimension,
        "textModel": embedded.text_model,
        "imageModel": embedded.image_model,
    }


def index_action(event: dict[str, Any]) -> dict[str, Any]:
    """Stage 3: persist vectors, parents, postings, catalog and manifest."""
    config = config_from_dict(load_config(), event.get("config"))
    logger.info(
        "index started",
        extra={
            "documentId": event["documentId"],
            "knowledgeBaseId": event["knowledgeBaseId"],
            "stage": "indexed",
        },
    )
    indexed = index_document(
        _storage(),
        config,
        user_id=event["userId"],
        knowledge_base_id=event["knowledgeBaseId"],
        document_id=event["documentId"],
        chunks_key=event["chunksKey"],
        embeddings_key=event["embeddingsKey"],
        images=event.get("images") or [],
    )
    set_document_status(
        event["documentId"],
        "ready",
        chunk_count=indexed.chunk_count,
        image_count=indexed.image_count,
        embed_model=config.text_embed_model,
        image_embed_model=config.image_embed_model if indexed.image_count else None,
    )
    emit_event(
        document_id=event["documentId"],
        knowledge_base_id=event["knowledgeBaseId"],
        user_id=event["userId"],
        stage="indexed",
        status="succeeded",
        message=(
            f"{indexed.chunk_count} chunk{'s' if indexed.chunk_count != 1 else ''} · "
            f"{indexed.image_count} image{'s' if indexed.image_count != 1 else ''} indexed"
        ),
        details={
            "vectors": indexed.chunk_count,
            "chunks": indexed.chunk_count,
            "parents": indexed.parent_count,
            "images": indexed.image_count,
            "dimension": config.embedding_dim,
            "store": "s3",
        },
    )
    logger.info(
        "index succeeded",
        extra={
            "documentId": event["documentId"],
            "knowledgeBaseId": event["knowledgeBaseId"],
            "stage": "indexed",
        },
    )
    return {
        "chunkCount": indexed.chunk_count,
        "imageCount": indexed.image_count,
        "parentCount": indexed.parent_count,
    }


def mark_failed_action(event: dict[str, Any]) -> dict[str, Any]:
    """Failure handler: mark the document failed and record the failed stage."""
    failed_stage = event.get("stage") or "unknown"
    message = _error_message(event.get("error"))
    logger.error(
        f"ingestion failed: {message}",
        extra={
            "documentId": event.get("documentId"),
            "knowledgeBaseId": event.get("knowledgeBaseId"),
            "stage": failed_stage,
        },
    )
    set_document_status(event["documentId"], "failed")
    emit_event(
        document_id=event["documentId"],
        knowledge_base_id=event["knowledgeBaseId"],
        user_id=event["userId"],
        stage="failed",
        status="failed",
        message=f"{failed_stage}: {message}",
        details={"failedStage": failed_stage},
    )
    return {"ok": True}


def watchdog_action(event: dict[str, Any] | None = None) -> dict[str, Any]:
    """Scheduled safety net: fail documents stuck in ``processing``."""
    threshold = int(os.environ.get("STALL_THRESHOLD_MINUTES", "75"))
    stalled = find_stalled_documents(threshold)
    for document in stalled:
        logger.warning(
            "reaping stalled document",
            extra={
                "documentId": document["id"],
                "knowledgeBaseId": document["knowledge_base_id"],
                "stage": "failed",
            },
        )
        set_document_status(document["id"], "failed")
        emit_event(
            document_id=document["id"],
            knowledge_base_id=document["knowledge_base_id"],
            user_id=document["user_id"],
            stage="failed",
            status="failed",
            message=(
                f"stalled: no progress for over {threshold} minutes "
                f"({document['file_name']})"
            ),
            details={"failedStage": "stalled", "reason": "watchdog"},
            file_name=document.get("file_name"),
        )
    logger.info(
        "watchdog scan complete",
        extra={"reaped": len(stalled), "thresholdMinutes": threshold},
    )
    return {"reaped": len(stalled), "thresholdMinutes": threshold}
