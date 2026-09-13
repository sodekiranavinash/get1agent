from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text

from shared.db.session import get_session
from shared.ingestion.chunking import chunk_text
from shared.ingestion.config import IngestionConfig, load_config
from shared.ingestion.embeddings import embed_images, embed_texts
from shared.ingestion.extractors import Extraction, extract
from shared.models import Document, IngestionEvent, KnowledgeBase
from shared.storage import Storage

DERIVED_DIR = ".derived"
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
        overrides: dict[str, object] = {
            "embedding_dim": knowledge_base.embedding_dim or base.embedding_dim,
            "chunk_size": knowledge_base.chunk_size or base.chunk_size,
            "chunk_overlap": (
                knowledge_base.chunk_overlap
                if knowledge_base.chunk_overlap is not None
                else base.chunk_overlap
            ),
        }
        # Bedrock model ids come from the KB. Local (Ollama) embeddings use
        # LOCAL_EMBED_MODEL instead, so keep the env-provided model name.
        if base.embed_mode == "bedrock":
            overrides["text_embed_model"] = (
                knowledge_base.embed_model or base.text_embed_model
            )
            overrides["image_embed_model"] = (
                knowledge_base.image_embed_model or base.image_embed_model
            )
        return replace(base, **overrides)


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


async def find_stalled_documents(threshold_minutes: int) -> list[dict]:
    """Documents left in ``processing`` with no update for ``threshold_minutes``.

    The watchdog uses this to fail documents whose execution was aborted (e.g.
    the state machine hit its ``TimeoutSeconds``) before the failure handler
    could run. The threshold must exceed the state machine timeout so the
    watchdog never races a still-running execution.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
    async with get_session() as session:
        result = await session.execute(
            select(Document).where(
                Document.status == "processing",
                Document.updated_at < cutoff,
            )
        )
        return [
            {
                "id": str(document.id),
                "knowledge_base_id": str(document.knowledge_base_id),
                "user_id": str(document.user_id),
                "file_name": document.file_name,
            }
            for document in result.scalars()
        ]


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


def _extraction_stats(
    extraction: Extraction, selected_images: int, source_bytes: int
) -> dict:
    """Shape of what was parsed, for the ingestion timeline.

    Numeric only (the UI formats units) and None fields dropped so the event
    payload stays small and format-specific.
    """
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
    """Download, extract text + images, and stage derived artifacts in storage."""
    raw = storage.get_bytes(s3_key)
    extraction = extract(raw, file_name)

    prefix = _derived_prefix(user_id, knowledge_base_id, document_id)
    text_key = f"{prefix}/text.md"
    storage.put_bytes(text_key, extraction.text.encode("utf-8"), "text/markdown")

    # Chunking is pure CPU: do it here (the extract worker is in the VPC and
    # already loaded the per-KB chunk settings) so the embed worker can stay
    # outside the VPC and just turn text into vectors.
    chunks = chunk_text(extraction.text, config.chunk_size, config.chunk_overlap)
    chunks_key = f"{prefix}/{CHUNKS_FILENAME}"
    storage.put_bytes(
        chunks_key,
        json.dumps({"chunks": chunks}).encode("utf-8"),
        "application/json",
    )
    chunk_stats = {
        "chunks": len(chunks),
        "characters": sum(len(chunk) for chunk in chunks),
        "tokens": sum(max(1, len(chunk) // 4) for chunk in chunks),
        "chunkSize": config.chunk_size,
        "chunkOverlap": config.chunk_overlap,
    }

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
    """Turn staged chunk text + images into vectors and stage the result.

    Runs outside the VPC: it only needs S3 (public) and Bedrock (public), so it
    never touches RDS. The vectors are written back to S3 for the in-VPC index
    worker to persist.
    """
    payload = json.loads(storage.get_bytes(chunks_key).decode("utf-8"))
    chunks = payload.get("chunks") or []
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


async def index_document(
    storage: Storage,
    config: IngestionConfig,
    *,
    user_id: str,
    knowledge_base_id: str,
    document_id: str,
    chunks_key: str,
    embeddings_key: str,
    images: list[dict],
) -> IndexedDocument:
    """Persist the embed stage's vectors (and chunk text) into pgvector."""
    chunks = json.loads(storage.get_bytes(chunks_key).decode("utf-8")).get(
        "chunks"
    ) or []
    artifact = json.loads(storage.get_bytes(embeddings_key).decode("utf-8"))
    chunk_vectors = artifact.get("chunkVectors") or []
    image_vectors = artifact.get("imageVectors") or []

    embedding_count = len(chunk_vectors) + len(image_vectors)
    await emit_event(
        document_id=document_id,
        knowledge_base_id=knowledge_base_id,
        user_id=user_id,
        stage="embedding",
        status="succeeded",
        message=(
            f"{embedding_count} embedding{'s' if embedding_count != 1 else ''} "
            f"({len(chunk_vectors)} text"
            + (f" · {len(image_vectors)} image" if image_vectors else "")
            + ")"
        ),
        details={
            "embeddings": embedding_count,
            "textEmbeddings": len(chunk_vectors),
            "imageEmbeddings": len(image_vectors),
            "dimension": config.embedding_dim,
            "model": config.text_embed_model,
        },
    )

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

    return IndexedDocument(chunk_count=len(chunks), image_count=len(image_vectors))
