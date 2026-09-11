from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field, replace

from sqlalchemy import func, select, text

from shared.db.session import get_session
from shared.ingestion.chunking import chunk_text
from shared.ingestion.config import IngestionConfig, load_config
from shared.ingestion.embeddings import embed_images, embed_texts
from shared.ingestion.extractors import Extraction, extract
from shared.models import Document, IngestionEvent, KnowledgeBase
from shared.storage import Storage

DERIVED_DIR = ".derived"

_IMAGE_CONTENT_TYPES = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
    "webp": "image/webp",
}

_INSERT_CHUNK = text(
    """
    INSERT INTO chunks (
        document_id, knowledge_base_id, user_id, ordinal, chunk_hash,
        content, token_count, embedding
    )
    VALUES (
        :document_id, :knowledge_base_id, :user_id, :ordinal, :chunk_hash,
        :content, :token_count, CAST(CAST(:embedding AS text) AS vector)
    )
    ON CONFLICT (document_id, chunk_hash) DO NOTHING
    """
)

_INSERT_IMAGE = text(
    """
    INSERT INTO document_images (
        document_id, knowledge_base_id, user_id, s3_key, page, width,
        height, content_hash, embedding
    )
    VALUES (
        :document_id, :knowledge_base_id, :user_id, :s3_key, :page, :width,
        :height, :content_hash, CAST(CAST(:embedding AS text) AS vector)
    )
    ON CONFLICT (document_id, content_hash) DO NOTHING
    """
)


@dataclass
class ExtractedDocument:
    text_key: str
    images: list[dict] = field(default_factory=list)

    @property
    def image_count(self) -> int:
        return len(self.images)


@dataclass
class IndexedDocument:
    chunk_count: int
    image_count: int


def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(repr(float(item)) for item in values) + "]"


def _derived_prefix(user_id: str, kb_id: str, document_id: str) -> str:
    return f"{user_id}/{kb_id}/{document_id}/{DERIVED_DIR}"


async def load_config_for_knowledge_base(
    knowledge_base_id: str | uuid.UUID,
) -> IngestionConfig:
    """Per-KB settings, falling back to the workspace/environment defaults."""
    base = load_config()
    async with get_session() as session:
        knowledge_base = await session.get(
            KnowledgeBase, _as_uuid(knowledge_base_id)
        )
        if knowledge_base is None:
            return base
        return replace(
            base,
            text_embed_model=knowledge_base.embed_model or base.text_embed_model,
            image_embed_model=knowledge_base.image_embed_model
            or base.image_embed_model,
            embedding_dim=knowledge_base.embedding_dim or base.embedding_dim,
            chunk_size=knowledge_base.chunk_size or base.chunk_size,
            chunk_overlap=(
                knowledge_base.chunk_overlap
                if knowledge_base.chunk_overlap is not None
                else base.chunk_overlap
            ),
        )


async def emit_event(
    *,
    document_id: str | uuid.UUID,
    knowledge_base_id: str | uuid.UUID,
    user_id: str | uuid.UUID,
    stage: str,
    status: str,
    message: str | None = None,
    details: dict | None = None,
) -> None:
    async with get_session() as session:
        session.add(
            IngestionEvent(
                document_id=_as_uuid(document_id),
                knowledge_base_id=_as_uuid(knowledge_base_id),
                user_id=_as_uuid(user_id),
                stage=stage,
                status=status,
                message=message,
                details=details,
            )
        )
        await session.commit()


async def get_document(document_id: str | uuid.UUID) -> dict | None:
    """Return the fields the worker needs to process a document."""
    async with get_session() as session:
        document = await session.get(Document, _as_uuid(document_id))
        if document is None:
            return None
        return {
            "id": str(document.id),
            "status": document.status,
            "s3_key": document.s3_key,
            "file_name": document.file_name,
            "content_type": document.content_type,
            "knowledge_base_id": str(document.knowledge_base_id),
            "user_id": str(document.user_id),
        }


async def set_document_status(
    document_id: str | uuid.UUID,
    status: str,
    *,
    chunk_count: int | None = None,
    image_count: int | None = None,
    embed_model: str | None = None,
    image_embed_model: str | None = None,
) -> None:
    async with get_session() as session:
        document = await session.get(Document, _as_uuid(document_id))
        if document is None:
            return
        document.status = status
        if chunk_count is not None:
            document.chunk_count = chunk_count
        if image_count is not None:
            document.image_count = image_count
        if embed_model is not None:
            document.embed_model = embed_model
        if image_embed_model is not None:
            document.image_embed_model = image_embed_model
        await session.flush()

        processing = await session.scalar(
            select(func.count())
            .select_from(Document)
            .where(
                Document.knowledge_base_id == document.knowledge_base_id,
                Document.status == "processing",
            )
        )
        knowledge_base = await session.get(KnowledgeBase, document.knowledge_base_id)
        if knowledge_base is not None:
            knowledge_base.status = "processing" if (processing or 0) > 0 else "ready"
        await session.commit()


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
    """Download, extract text + images, and stage derived artifacts in storage."""
    raw = storage.get_bytes(s3_key)
    extraction = extract(raw, file_name)

    prefix = _derived_prefix(user_id, knowledge_base_id, document_id)
    text_key = f"{prefix}/text.md"
    storage.put_bytes(text_key, extraction.text.encode("utf-8"), "text/markdown")

    images: list[dict] = []
    for index, (data, extension, page, width, height) in enumerate(
        _select_images(extraction, config)
    ):
        digest = hashlib.sha256(data).hexdigest()
        key = f"{prefix}/images/{page or 0}-{index}.{extension}"
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

    return ExtractedDocument(text_key=text_key, images=images)


async def index_document(
    storage: Storage,
    config: IngestionConfig,
    *,
    user_id: str,
    knowledge_base_id: str,
    document_id: str,
    text_key: str,
    images: list[dict],
) -> IndexedDocument:
    """Chunk + embed text and images, then replace this document's rows."""
    text_content = storage.get_bytes(text_key).decode("utf-8")
    chunks = chunk_text(text_content, config.chunk_size, config.chunk_overlap)

    await emit_event(
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
        user_id=user_id,
        stage="chunked",
        status="succeeded",
        message=f"{len(chunks)} chunk{'s' if len(chunks) != 1 else ''}",
    )

    await emit_event(
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
        user_id=user_id,
        stage="embedding",
        status="started",
        message=f"Embedding {len(chunks)} text chunks",
    )
    chunk_vectors = embed_texts(chunks, config)

    image_vectors: list[list[float]] = []
    if images:
        blobs = [storage.get_bytes(image["key"]) for image in images]
        image_vectors = embed_images(blobs, config)

    document_uuid = _as_uuid(document_id)
    kb_uuid = _as_uuid(knowledge_base_id)
    user_uuid = _as_uuid(user_id)

    async with get_session() as session:
        await session.execute(
            text("DELETE FROM chunks WHERE document_id = :id"), {"id": document_uuid}
        )
        await session.execute(
            text("DELETE FROM document_images WHERE document_id = :id"),
            {"id": document_uuid},
        )

        for ordinal, (chunk, vector) in enumerate(zip(chunks, chunk_vectors)):
            await session.execute(
                _INSERT_CHUNK,
                {
                    "document_id": document_uuid,
                    "knowledge_base_id": kb_uuid,
                    "user_id": user_uuid,
                    "ordinal": ordinal,
                    "chunk_hash": hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
                    "content": chunk,
                    "token_count": max(1, len(chunk) // 4),
                    "embedding": _vector_literal(vector),
                },
            )

        for image, vector in zip(images, image_vectors):
            await session.execute(
                _INSERT_IMAGE,
                {
                    "document_id": document_uuid,
                    "knowledge_base_id": kb_uuid,
                    "user_id": user_uuid,
                    "s3_key": image["key"],
                    "page": image.get("page"),
                    "width": image.get("width"),
                    "height": image.get("height"),
                    "content_hash": image["hash"],
                    "embedding": _vector_literal(vector),
                },
            )

        await session.commit()

    return IndexedDocument(chunk_count=len(chunks), image_count=len(images))


async def ingest_document(
    *,
    user_id: str,
    knowledge_base_id: str,
    document_id: str,
    s3_key: str,
    file_name: str,
    storage: Storage | None = None,
    config: IngestionConfig | None = None,
) -> IndexedDocument:
    """Extract + index in one call. Used by local mode (no SQS/Step Functions)."""
    storage = storage or Storage()
    config = config or await load_config_for_knowledge_base(knowledge_base_id)

    await set_document_status(document_id, "processing")
    try:
        extracted = extract_document(
            storage,
            config,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            s3_key=s3_key,
            file_name=file_name,
        )
        await emit_event(
            document_id=document_id,
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
            stage="extracted",
            status="succeeded",
            message=(
                f"{extracted.image_count} image{'s' if extracted.image_count != 1 else ''}"
            ),
        )
        indexed = await index_document(
            storage,
            config,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
            text_key=extracted.text_key,
            images=extracted.images,
        )
        await set_document_status(
            document_id,
            "ready",
            chunk_count=indexed.chunk_count,
            image_count=indexed.image_count,
            embed_model=config.text_embed_model,
            image_embed_model=config.image_embed_model if indexed.image_count else None,
        )
        await emit_event(
            document_id=document_id,
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
            stage="indexed",
            status="succeeded",
            message=(
                f"{indexed.chunk_count} chunks · {indexed.image_count} images indexed"
            ),
        )
        return indexed
    except Exception as exc:  # noqa: BLE001 - surfaced to the event feed
        await set_document_status(document_id, "failed")
        await emit_event(
            document_id=document_id,
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
            stage="failed",
            status="failed",
            message=str(exc),
        )
        raise
