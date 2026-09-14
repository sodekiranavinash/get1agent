from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any

from shared.dynamo.repositories import documents as documents_repo
from shared.dynamo.repositories import events as events_repo
from shared.dynamo.repositories import knowledge_bases as kb_repo
from shared.ingestion.chunking import chunk_parents
from shared.ingestion.config import IngestionConfig, load_config
from shared.ingestion.embeddings import embed_images, embed_texts
from shared.ingestion.extractors import Extraction, extract
from shared.search import layout
from shared.search.maintenance import delete_document_index
from shared.search.s3_vectors import VectorRecord, vector_store
from shared.search.term_index import add_postings, build_postings, update_catalog, update_stats
from shared.storage import Storage

CHUNKS_FILENAME = "chunks.json"
EMBEDDINGS_FILENAME = "embeddings.json"

_IMAGE_CONTENT_TYPES = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
    "webp": "image/webp",
}


@dataclass
class ExtractedDocument:
    text_key: str
    chunks_key: str
    images: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    chunk_stats: dict = field(default_factory=dict)

    @property
    def image_count(self) -> int:
        return len(self.images)

    @property
    def chunk_count(self) -> int:
        return int(self.chunk_stats.get("chunks", 0))

    @property
    def parent_count(self) -> int:
        return int(self.chunk_stats.get("parents", 0))


@dataclass
class EmbeddedDocument:
    """Vectors computed by the (non-VPC) embed stage, staged in S3."""

    embeddings_key: str
    chunk_count: int
    image_count: int
    dimension: int
    text_model: str
    image_model: str


@dataclass
class IndexedDocument:
    chunk_count: int
    image_count: int
    parent_count: int = 0


def _chunk_records(payload: dict) -> list[dict]:
    """Normalize a staged ``chunks.json`` payload into chunk records."""
    records: list[dict] = []
    for item in payload.get("chunks") or []:
        if isinstance(item, dict):
            records.append(item)
        else:
            records.append(
                {"text": item, "page": None, "pageEnd": None, "parentOrdinal": None}
            )
    return records


def _parent_records(payload: dict) -> list[dict]:
    return [
        item
        for item in payload.get("parents") or []
        if isinstance(item, dict) and item.get("text")
    ]


def load_config_for_knowledge_base(knowledge_base_id: str) -> IngestionConfig:
    """Per-KB settings, falling back to the workspace/environment defaults."""
    base = load_config()
    knowledge_base = kb_repo.get_kb_by_id(knowledge_base_id)
    if knowledge_base is None:
        return base
    # DynamoDB numbers come back as Decimal; the chunker needs ints.
    overrides: dict[str, object] = {
        "embedding_dim": int(knowledge_base.get("embeddingDim") or base.embedding_dim),
        "chunk_size": int(knowledge_base.get("chunkSize") or base.chunk_size),
        "chunk_overlap": (
            int(knowledge_base["chunkOverlap"])
            if knowledge_base.get("chunkOverlap") is not None
            else base.chunk_overlap
        ),
    }
    # Bedrock model ids come from the KB. Local (Ollama) embeddings use
    # LOCAL_EMBED_MODEL instead, so keep the env-provided model name.
    if base.embed_mode == "bedrock":
        overrides["text_embed_model"] = (
            knowledge_base.get("embedModel") or base.text_embed_model
        )
        overrides["image_embed_model"] = (
            knowledge_base.get("imageEmbedModel") or base.image_embed_model
        )
    return replace(base, **overrides)


def emit_event(
    *,
    document_id: str,
    knowledge_base_id: str,
    user_id: str,
    stage: str,
    status: str,
    message: str | None = None,
    details: dict | None = None,
    file_name: str | None = None,
    file_key: str | None = None,
) -> None:
    # Every event must carry the document's fileName + fileKey so the events
    # feed can associate it with a document (and its live status) without the
    # caller having to thread them through the whole pipeline.
    if file_name is None or file_key is None:
        document = documents_repo.get_document_by_id(document_id)
        if document:
            file_name = file_name or document.get("fileName")
            file_key = file_key or document.get("fileKey")
    events_repo.emit_event(
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
        user_id=user_id,
        stage=stage,
        status=status,
        message=message,
        details=details,
        file_name=file_name,
        file_key=file_key,
    )


def get_document(document_id: str) -> dict | None:
    """Return the fields the worker needs to process a document."""
    document = documents_repo.get_document_by_id(document_id)
    if document is None:
        return None
    return {
        "id": document["docId"],
        "status": document["status"],
        "s3_key": document["s3Key"],
        "file_name": document["fileName"],
        "content_type": document.get("contentType"),
        "knowledge_base_id": document["kbId"],
        "user_id": document["userId"],
    }


def find_stalled_documents(threshold_minutes: int) -> list[dict]:
    """Documents left in ``processing`` with no update for ``threshold_minutes``."""
    cutoff = (
        datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
    ).isoformat()
    documents = documents_repo.find_by_status_older_than("processing", cutoff)
    return [
        {
            "id": document["docId"],
            "knowledge_base_id": document["kbId"],
            "user_id": document["userId"],
            "file_name": document.get("fileName"),
        }
        for document in documents
    ]


def set_document_status(
    document_id: str,
    status: str,
    *,
    chunk_count: int | None = None,
    image_count: int | None = None,
    embed_model: str | None = None,
    image_embed_model: str | None = None,
) -> None:
    document = documents_repo.get_document_by_id(document_id)
    if document is None:
        return
    old_status = document.get("status")
    fields: dict[str, Any] = {"status": status}
    if chunk_count is not None:
        fields["chunkCount"] = chunk_count
    if image_count is not None:
        fields["imageCount"] = image_count
    if embed_model is not None:
        fields["embedModel"] = embed_model
    if image_embed_model is not None:
        fields["imageEmbedModel"] = image_embed_model
    documents_repo.update_document(document_id, **fields)

    if old_status != status:
        delta = (1 if status == "processing" else 0) - (
            1 if old_status == "processing" else 0
        )
        if delta:
            kb_repo.adjust_processing(document["kbId"], delta)


def _select_images(
    extraction: Extraction, config: IngestionConfig
) -> list[tuple[bytes, str, int | None, int | None, str]]:
    selected: list[tuple[bytes, str, int | None, int | None, str]] = []
    seen: set[str] = set()
    for image in extraction.images:
        if len(image.data) < config.min_image_bytes:
            continue
        if (
            image.width
            and image.height
            and min(image.width, image.height) < config.min_image_dimension
        ):
            continue
        digest = hashlib.sha256(image.data).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        selected.append((image.data, image.extension, image.page, image.width, image.height))
        if len(selected) >= config.max_images_per_doc:
            break
    return selected


def _extraction_stats(
    extraction: Extraction, selected_images: int, source_bytes: int
) -> dict:
    text = extraction.text
    stats: dict[str, int] = {
        "sourceBytes": source_bytes,
        "characters": len(text),
        "words": len(text.split()),
        "images": selected_images,
        "imagesFound": len(extraction.images),
    }
    for key, value in (
        ("pages", extraction.pages),
        ("rows", extraction.rows),
        ("sheets", extraction.sheets),
        ("paragraphs", extraction.paragraphs),
    ):
        if value is not None:
            stats[key] = value
    return stats


def extract_document(
    storage: Storage,
    config: IngestionConfig,
    *,
    user_id: str,
    knowledge_base_id: str,
    document_id: str,
    s3_key: str,
    file_name: str,
) -> ExtractedDocument:
    """Download, extract text + images, chunk, and stage derived artifacts."""
    raw = storage.get_bytes(s3_key)
    extraction = extract(raw, file_name)

    text_key = layout.text_key(user_id, knowledge_base_id, document_id)
    storage.put_bytes(text_key, extraction.text.encode("utf-8"), "text/markdown")

    parents = chunk_parents(
        extraction.text,
        chunk_size=config.chunk_size,
        overlap=config.chunk_overlap,
        parent_size=config.parent_size,
        page_texts=extraction.page_texts,
    )
    parent_records: list[dict] = []
    chunk_records: list[dict] = []
    for ordinal, parent in enumerate(parents):
        parent_records.append(
            {
                "ordinal": ordinal,
                "page": parent.page,
                "pageEnd": parent.page_end,
                "text": parent.text,
            }
        )
        for child in parent.children:
            chunk_records.append(
                {
                    "text": child.text,
                    "page": child.page,
                    "pageEnd": child.page_end,
                    "parentOrdinal": ordinal,
                }
            )
    chunks_key = layout.chunks_key(user_id, knowledge_base_id, document_id)
    storage.put_bytes(
        chunks_key,
        json.dumps({"parents": parent_records, "chunks": chunk_records}).encode("utf-8"),
        "application/json",
    )
    chunk_stats = {
        "chunks": len(chunk_records),
        "parents": len(parent_records),
        "characters": sum(len(record["text"]) for record in chunk_records),
        "tokens": sum(max(1, len(record["text"]) // 4) for record in chunk_records),
        "chunkSize": config.chunk_size,
        "chunkOverlap": config.chunk_overlap,
    }

    images: list[dict] = []
    for index, (data, extension, page, width, height) in enumerate(
        _select_images(extraction, config)
    ):
        digest = hashlib.sha256(data).hexdigest()
        key = layout.image_key(user_id, knowledge_base_id, document_id, page, index, extension)
        content_type = _IMAGE_CONTENT_TYPES.get(extension.lower(), "application/octet-stream")
        storage.put_bytes(key, data, content_type)
        images.append(
            {
                "key": key,
                "page": page,
                "width": width,
                "height": height,
                "hash": digest,
            }
        )

    return ExtractedDocument(
        text_key=text_key,
        chunks_key=chunks_key,
        images=images,
        stats=_extraction_stats(extraction, len(images), len(raw)),
        chunk_stats=chunk_stats,
    )


def embed_document(
    storage: Storage,
    config: IngestionConfig,
    *,
    chunks_key: str,
    images: list[dict],
) -> EmbeddedDocument:
    """Turn staged chunk text + images into vectors and stage the result."""
    payload = json.loads(storage.get_bytes(chunks_key).decode("utf-8"))
    records = _chunk_records(payload)
    chunks = [record["text"] for record in records]
    chunk_vectors = embed_texts(chunks, config)

    image_vectors: list[list[float]] = []
    if images:
        blobs = [storage.get_bytes(image["key"]) for image in images]
        image_vectors = embed_images(blobs, config)

    embeddings_key = f"{chunks_key.rsplit('/', 1)[0]}/{EMBEDDINGS_FILENAME}"
    artifact = {
        "dimension": config.embedding_dim,
        "textModel": config.text_embed_model,
        "imageModel": config.image_embed_model,
        "chunkVectors": chunk_vectors,
        "imageVectors": image_vectors,
    }
    storage.put_bytes(
        embeddings_key,
        json.dumps(artifact).encode("utf-8"),
        "application/json",
    )
    return EmbeddedDocument(
        embeddings_key=embeddings_key,
        chunk_count=len(chunks),
        image_count=len(image_vectors),
        dimension=config.embedding_dim,
        text_model=config.text_embed_model,
        image_model=config.image_embed_model,
    )


def _chunk_id(document_id: str, ordinal: int) -> str:
    return f"{document_id}#{ordinal}"


def _parent_id(document_id: str, ordinal: int) -> str:
    return f"{document_id}#{ordinal}"


def index_document(
    storage: Storage,
    config: IngestionConfig,
    *,
    user_id: str,
    knowledge_base_id: str,
    document_id: str,
    chunks_key: str,
    embeddings_key: str,
    images: list[dict],
    file_name: str | None = None,
    kb_name: str | None = None,
    content_type: str | None = None,
) -> IndexedDocument:
    """Persist vectors (S3 Vectors/local), parents, postings, catalog + manifest."""
    payload = json.loads(storage.get_bytes(chunks_key).decode("utf-8"))
    records = _chunk_records(payload)
    parents = _parent_records(payload)
    artifact = json.loads(storage.get_bytes(embeddings_key).decode("utf-8"))
    chunk_vectors = artifact.get("chunkVectors") or []
    image_vectors = artifact.get("imageVectors") or []

    if file_name is None or kb_name is None:
        document = documents_repo.get_document_by_id(document_id)
        knowledge_base = kb_repo.get_kb_by_id(knowledge_base_id)
        file_name = file_name or (document or {}).get("fileName") or ""
        content_type = content_type or (document or {}).get("contentType")
        kb_name = kb_name or (knowledge_base or {}).get("name") or ""

    store = vector_store(storage)
    # Idempotent re-index: drop anything a previous run left behind.
    delete_document_index(storage, store, user_id, document_id)

    # Map each child chunk to its parent, preserving order.
    parent_children: dict[int, list[dict]] = {}
    chunk_to_parent: dict[int, int] = {}
    for ordinal, record in enumerate(records):
        parent_ordinal = record.get("parentOrdinal")
        if parent_ordinal is None:
            continue
        chunk_to_parent[ordinal] = int(parent_ordinal)
        parent_children.setdefault(int(parent_ordinal), []).append(
            {
                "chunkId": _chunk_id(document_id, ordinal),
                "ordinal": ordinal,
                "text": record["text"],
                "page": record.get("page"),
                "pageEnd": record.get("pageEnd"),
                "tokenCount": max(1, len(record["text"]) // 4),
            }
        )

    vectors: list[VectorRecord] = []
    postings: dict[str, dict] = {}
    chunk_ids: list[str] = []
    total_tokens = 0

    for ordinal, (record, vector) in enumerate(zip(records, chunk_vectors)):
        text = record["text"]
        chunk_id = _chunk_id(document_id, ordinal)
        parent_id = (
            _parent_id(document_id, chunk_to_parent[ordinal])
            if ordinal in chunk_to_parent
            else None
        )
        chunk_ids.append(chunk_id)
        token_count = max(1, len(text) // 4)
        filterable: dict[str, Any] = {
            "kbId": knowledge_base_id,
            "docId": document_id,
            "status": "ready",
            "tokenCount": token_count,
        }
        if record.get("page") is not None:
            filterable["page"] = int(record["page"])
        if parent_id:
            filterable["parentId"] = parent_id
        vectors.append(
            VectorRecord(
                key=chunk_id,
                vector=[float(value) for value in vector],
                filterable=filterable,
                non_filterable={
                    "text": text,
                    "kbName": kb_name,
                    "fileName": file_name,
                },
            )
        )
        chunk_postings = build_postings(
            chunk_id=chunk_id,
            doc_id=document_id,
            kb_id=knowledge_base_id,
            parent_id=parent_id or "",
            text=text,
        )
        if chunk_postings:
            total_tokens += next(iter(chunk_postings.values()))["dl"]
        postings.update(chunk_postings)

    store.upsert(user_id, vectors)

    parent_ids: list[str] = []
    for parent in parents:
        ordinal = int(parent.get("ordinal", len(parent_ids)))
        parent_id = _parent_id(document_id, ordinal)
        parent_ids.append(parent_id)
        storage.put_json(
            layout.parent_key(user_id, parent_id),
            {
                "parentId": parent_id,
                "docId": document_id,
                "kbId": knowledge_base_id,
                "userId": user_id,
                "fileName": file_name,
                "kbName": kb_name,
                "contentType": content_type,
                "ordinal": ordinal,
                "page": parent.get("page"),
                "pageEnd": parent.get("pageEnd"),
                "content": parent["text"],
                "tokenCount": max(1, len(parent["text"]) // 4),
                "children": parent_children.get(ordinal, []),
            },
        )

    if postings:
        add_postings(storage, user_id, postings)
        update_catalog(storage, user_id, list(postings.keys()))
    update_stats(
        storage,
        user_id,
        delta_chunks=len(chunk_ids),
        delta_tokens=total_tokens,
    )
    storage.put_json(
        layout.manifest_key(user_id, document_id),
        {
            "docId": document_id,
            "kbId": knowledge_base_id,
            "userId": user_id,
            "chunkIds": chunk_ids,
            "parentIds": parent_ids,
            "tokens": list(postings.keys()),
            "totalTokens": total_tokens,
        },
    )

    return IndexedDocument(
        chunk_count=len(records),
        image_count=len(image_vectors),
        parent_count=len(parents),
    )
