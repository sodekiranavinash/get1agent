import base64
import hashlib
import json
import os
import re
import sys
import traceback
import uuid
from typing import Any
from urllib.parse import parse_qs

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ai.auth import AuthError, require_user
from shared.db.engine import run_async
from shared.db.session import get_session
from shared.ingestion import emit_event, load_config
from shared.ingestion.config import (
    SUPPORTED_IMAGE_EMBED_MODELS,
    SUPPORTED_TEXT_EMBED_MODELS,
)
from shared.models import Document, DocumentTag, IngestionEvent, KnowledgeBase
from shared.models.document_tag import MAX_TAGS_PER_DOCUMENT
from shared.quotas import Quota, get_quota
from shared.users import get_or_create_user

# --- limits / supported formats ---------------------------------------------

ALLOWED_EXTENSIONS: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
    ".csv": {"text/csv", "application/csv", "application/vnd.ms-excel"},
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    },
}

DEFAULT_CONTENT_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

PRESIGN_EXPIRES_SECONDS = 3600
MAX_NAME_LENGTH = 255
MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 1000
MAX_TAG_NAME_LENGTH = 64
MAX_TAG_DESCRIPTION_LENGTH = 500


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# --- event helpers ----------------------------------------------------------


def _json(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _claims(event: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]
    except (KeyError, TypeError):
        return None


def _method(event: dict[str, Any]) -> str:
    method = event.get("requestContext", {}).get("http", {}).get(
        "method", event.get("httpMethod", "GET")
    )
    return str(method).upper()


def _path(event: dict[str, Any]) -> str:
    raw = event.get("rawPath") or event.get("path") or ""
    return raw.split("?", 1)[0].rstrip("/")


def _segments(event: dict[str, Any]) -> list[str]:
    return [segment for segment in _path(event).split("/") if segment]


def _body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body")
    if not raw:
        return {}
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ApiError(400, "Request body must be a JSON object")
    return parsed


def _query(event: dict[str, Any]) -> dict[str, str]:
    raw = event.get("rawQueryString") or ""
    if raw:
        parsed = parse_qs(raw)
        return {key: values[0] for key, values in parsed.items() if values}
    params = event.get("queryStringParameters") or {}
    return {key: str(value) for key, value in params.items() if value is not None}


def _parse_uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError) as exc:
        raise ApiError(404, f"{label} not found") from exc


# --- storage -----------------------------------------------------------------


def _bucket() -> str | None:
    return os.environ.get("S3_BUCKET") or None


def _s3_client():
    import boto3
    from botocore.config import Config

    region = os.environ.get("S3_REGION") or os.environ.get("AWS_REGION")
    # Virtual-hosted addressing makes boto3 sign against the bucket's regional
    # endpoint (bucket.s3.<region>.amazonaws.com). With the default addressing
    # style it signs the global s3.amazonaws.com endpoint, and S3 answers
    # presigned requests with a 307 redirect to the region.
    return boto3.client(
        "s3",
        region_name=region,
        config=Config(s3={"addressing_style": "virtual"}),
    )


def _safe_filename(name: str) -> str:
    base = os.path.basename(name or "").strip()
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip()
    base = base.lstrip(".") or "file"
    return base[:MAX_TITLE_LENGTH]


def _extension(name: str) -> str:
    return os.path.splitext(name or "")[1].lower()


def _validate_file(file_name: str, content_type: str | None, size: int, quota: Quota) -> None:
    extension = _extension(file_name)
    allowed = ALLOWED_EXTENSIONS.get(extension)
    if not allowed:
        supported = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ApiError(400, f"Unsupported file type. Allowed: {supported}")
    if content_type:
        normalized = content_type.split(";", 1)[0].strip().lower()
        if normalized and normalized not in allowed and normalized != "application/octet-stream":
            raise ApiError(400, f"Content type {normalized} does not match {extension}")
    if size > quota.max_file_bytes:
        raise ApiError(413, "File exceeds the maximum allowed size")


def _build_key(user_id: uuid.UUID, kb_id: uuid.UUID, doc_id: uuid.UUID, file_name: str) -> str:
    return f"{user_id}/{kb_id}/{doc_id}/{_safe_filename(file_name)}"


def _presign_put(key: str, content_type: str) -> str:
    return _s3_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": _bucket(), "Key": key, "ContentType": content_type},
        ExpiresIn=PRESIGN_EXPIRES_SECONDS,
    )


def _presign_get(key: str) -> str | None:
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": key},
        ExpiresIn=PRESIGN_EXPIRES_SECONDS,
    )


def _put_object(key: str, data: bytes, content_type: str) -> None:
    _s3_client().put_object(
        Bucket=_bucket(), Key=key, Body=data, ContentType=content_type
    )


def _head_object(key: str) -> int:
    response = _s3_client().head_object(Bucket=_bucket(), Key=key)
    return int(response["ContentLength"])


def _object_etag(key: str) -> str | None:
    """Content fingerprint of the stored object, used as the ingestion idempotency key."""
    response = _s3_client().head_object(Bucket=_bucket(), Key=key)
    etag = response.get("ETag")
    return etag.strip('"') if etag else None


def _delete_object(key: str) -> None:
    _s3_client().delete_object(Bucket=_bucket(), Key=key)


def _delete_prefix(prefix: str) -> None:
    """Delete every object under ``prefix`` (original file + derived artifacts)."""
    client = _s3_client()
    bucket = _bucket()
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=bucket, Delete={"Objects": objects})


# --- validation --------------------------------------------------------------


def _validated_name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, f"{label} is required")
    name = value.strip()
    if len(name) > MAX_NAME_LENGTH:
        raise ApiError(400, f"{label} must be at most {MAX_NAME_LENGTH} characters")
    return name


# Knowledge base names follow S3-bucket-style rules so they are URL/command
# friendly and unambiguous when referenced by name from the MCP tools.
KB_NAME_MIN = 3
KB_NAME_MAX = 63
_KB_NAME_CHARS = re.compile(r"^[a-z0-9-]+$")
_KB_NAME_EDGES = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


def _validated_kb_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "Knowledge base name is required")
    name = value.strip()
    if len(name) < KB_NAME_MIN:
        raise ApiError(400, f"Name must be at least {KB_NAME_MIN} characters")
    if len(name) > KB_NAME_MAX:
        raise ApiError(400, f"Name must be at most {KB_NAME_MAX} characters")
    if not _KB_NAME_CHARS.match(name):
        raise ApiError(
            400,
            "Name can only contain lowercase letters, numbers and hyphens "
            "(no spaces or special characters)",
        )
    if not _KB_NAME_EDGES.match(name):
        raise ApiError(400, "Name must start and end with a letter or number")
    return name


# Chunking bounds. The UI offers presets but any value in range is accepted so
# a knowledge base can be tuned to its content (see the create dialog help).
MIN_CHUNK_SIZE = 128
MAX_CHUNK_SIZE = 4096
MIN_CHUNK_OVERLAP = 0
MAX_CHUNK_OVERLAP = 2048


def _validated_int_range(
    value: Any, label: str, default: int, minimum: int, maximum: int
) -> int:
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ApiError(400, f"{label} must be a whole number") from exc
    if number < minimum or number > maximum:
        raise ApiError(
            400, f"{label} must be between {minimum} and {maximum} tokens"
        )
    return number


def _validated_model(
    value: Any, allowed: tuple[str, ...], label: str, default: str
) -> str:
    if value is None or str(value).strip() == "":
        return default
    model = str(value).strip()
    if model not in allowed:
        raise ApiError(400, f"{label} must be one of {list(allowed)}")
    return model


def _parse_tags(raw: Any) -> list[tuple[str, str]]:
    """Tags are optional. Rows without a name are ignored; description is optional."""
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise ApiError(400, "tags must be a list")
    tags: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ApiError(400, "Each tag must be an object with name and description")
        name = str(item.get("name") or "").strip()
        description = str(item.get("description") or "").strip()
        if not name:
            continue
        if len(name) > MAX_TAG_NAME_LENGTH:
            raise ApiError(
                400, f"Tag name must be at most {MAX_TAG_NAME_LENGTH} characters"
            )
        if len(description) > MAX_TAG_DESCRIPTION_LENGTH:
            raise ApiError(
                400,
                f"Tag description must be at most {MAX_TAG_DESCRIPTION_LENGTH} characters",
            )
        if name.lower() in seen:
            raise ApiError(400, f"Duplicate tag: {name}")
        seen.add(name.lower())
        tags.append((name, description))
    if len(tags) > MAX_TAGS_PER_DOCUMENT:
        raise ApiError(400, f"At most {MAX_TAGS_PER_DOCUMENT} tags per file")
    return tags


def _make_tags(pairs: list[tuple[str, str]]) -> list[DocumentTag]:
    return [DocumentTag(name=name, description=description) for name, description in pairs]


# --- serialization -----------------------------------------------------------


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _serialize_document(document: Document, *, download_url: str | None = None) -> dict[str, Any]:
    return {
        "id": str(document.id),
        "knowledgeBaseId": str(document.knowledge_base_id),
        "fileName": document.file_name,
        "contentType": document.content_type,
        "sizeBytes": document.size_bytes,
        "source": document.source,
        "status": document.status,
        "chunkCount": document.chunk_count,
        "imageCount": document.image_count,
        "tags": [
            {"name": tag.name, "description": tag.description or ""}
            for tag in document.tags
        ],
        "createdAt": _iso(document.created_at),
        "updatedAt": _iso(document.updated_at),
        "downloadUrl": download_url,
    }


def _serialize_event(
    event: IngestionEvent, file_name: str, document_status: str
) -> dict[str, Any]:
    return {
        "id": event.id,
        "documentId": str(event.document_id),
        "knowledgeBaseId": str(event.knowledge_base_id),
        "fileName": file_name,
        "documentStatus": document_status,
        "stage": event.stage,
        "status": event.status,
        "message": event.message,
        "details": event.details,
        "createdAt": _iso(event.created_at),
    }


def _serialize_knowledge_base(kb: KnowledgeBase, file_count: int) -> dict[str, Any]:
    return {
        "id": str(kb.id),
        "name": kb.name,
        "description": kb.description,
        "status": kb.status,
        "fileCount": file_count,
        "embedModel": kb.embed_model,
        "imageEmbedModel": kb.image_embed_model,
        "embeddingDim": kb.embedding_dim,
        "chunkSize": kb.chunk_size,
        "chunkOverlap": kb.chunk_overlap,
        "createdAt": _iso(kb.created_at),
        "updatedAt": _iso(kb.updated_at),
    }


# --- data access -------------------------------------------------------------


async def _get_knowledge_base(session, user_id: uuid.UUID, kb_id: uuid.UUID) -> KnowledgeBase:
    kb = (
        await session.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == kb_id,
                KnowledgeBase.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if kb is None:
        raise ApiError(404, "Knowledge base not found")
    return kb


async def _document_count(session, kb_id: uuid.UUID) -> int:
    return int(
        (
            await session.execute(
                select(func.count(Document.id)).where(Document.knowledge_base_id == kb_id)
            )
        ).scalar_one()
    )


async def _user_document_count(session, user_id: uuid.UUID) -> int:
    return int(
        (
            await session.execute(
                select(func.count(Document.id)).where(Document.user_id == user_id)
            )
        ).scalar_one()
    )


async def _user_storage_bytes(session, user_id: uuid.UUID) -> int:
    return int(
        (
            await session.execute(
                select(func.coalesce(func.sum(Document.size_bytes), 0)).where(
                    Document.user_id == user_id
                )
            )
        ).scalar_one()
    )


async def _knowledge_base_count(session, user_id: uuid.UUID) -> int:
    return int(
        (
            await session.execute(
                select(func.count(KnowledgeBase.id)).where(
                    KnowledgeBase.user_id == user_id
                )
            )
        ).scalar_one()
    )


async def _get_document(session, kb_id: uuid.UUID, doc_id: uuid.UUID) -> Document:
    document = (
        await session.execute(
            select(Document)
            .options(selectinload(Document.tags))
            .where(Document.id == doc_id, Document.knowledge_base_id == kb_id)
        )
    ).scalar_one_or_none()
    if document is None:
        raise ApiError(404, "Document not found")
    return document


async def _assert_unique_file_name(
    session, kb_id: uuid.UUID, file_name: str
) -> None:
    """A knowledge base may not contain two files with the same name."""
    exists = (
        await session.execute(
            select(Document.id)
            .where(
                Document.knowledge_base_id == kb_id,
                func.lower(Document.file_name) == file_name.lower(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise ApiError(
            409, f'A file named "{file_name}" already exists in this knowledge base'
        )


async def _ensure_capacity(
    session,
    user_id: uuid.UUID,
    kb_id: uuid.UUID,
    quota: Quota,
    size_bytes: int,
) -> None:
    if await _document_count(session, kb_id) >= quota.max_files_per_kb:
        raise ApiError(
            409,
            f"This knowledge base already has the maximum of {quota.max_files_per_kb} files",
        )
    if await _user_document_count(session, user_id) >= quota.max_files_per_user:
        raise ApiError(
            409,
            f"You have reached the maximum of {quota.max_files_per_user} files",
        )
    used = await _user_storage_bytes(session, user_id)
    if used + size_bytes > quota.max_storage_bytes:
        raise ApiError(413, "You have reached your storage limit")


# --- handlers ----------------------------------------------------------------


async def _handle_list(claims: dict[str, Any]) -> dict[str, Any]:
    async with get_session() as session:
        user = await get_or_create_user(session, claims)
        rows = (
            await session.execute(
                select(KnowledgeBase, func.count(Document.id))
                .outerjoin(Document, Document.knowledge_base_id == KnowledgeBase.id)
                .where(KnowledgeBase.user_id == user.id)
                .group_by(KnowledgeBase.id)
                .order_by(KnowledgeBase.updated_at.desc())
            )
        ).all()
        quota = await get_quota(session, user.id)
        total_files = await _user_document_count(session, user.id)
        total_storage = await _user_storage_bytes(session, user.id)
        await session.commit()
        return _json(
            200,
            {
                "knowledgeBases": [
                    _serialize_knowledge_base(kb, count) for kb, count in rows
                ],
                "usage": {
                    "knowledgeBases": len(rows),
                    "files": total_files,
                    "storageBytes": total_storage,
                    "limits": {
                        "knowledgeBases": quota.max_knowledge_bases,
                        "filesPerKnowledgeBase": quota.max_files_per_kb,
                        "files": quota.max_files_per_user,
                        "storageBytes": quota.max_storage_bytes,
                        "fileBytes": quota.max_file_bytes,
                    },
                },
            },
        )


async def _handle_list_tags(claims: dict[str, Any]) -> dict[str, Any]:
    """Distinct tag names the user has used, for autocomplete suggestions."""
    async with get_session() as session:
        user = await get_or_create_user(session, claims)
        rows = (
            await session.execute(
                select(DocumentTag.name, DocumentTag.description)
                .join(Document, Document.id == DocumentTag.document_id)
                .where(Document.user_id == user.id)
                .distinct(DocumentTag.name)
                .order_by(DocumentTag.name, DocumentTag.created_at.desc())
            )
        ).all()
        await session.commit()
        return _json(
            200,
            {"tags": [{"name": name, "description": description or ""} for name, description in rows]},
        )


async def _handle_list_events(
    claims: dict[str, Any], query: dict[str, str]
) -> dict[str, Any]:
    try:
        limit = min(200, max(1, int(query.get("limit", "50"))))
    except ValueError:
        limit = 50

    kb_filter = query.get("kbId")
    kb_id: uuid.UUID | None = None
    if kb_filter:
        try:
            kb_id = uuid.UUID(kb_filter)
        except (ValueError, TypeError) as exc:
            raise ApiError(400, "Invalid kbId") from exc

    async with get_session() as session:
        user = await get_or_create_user(session, claims)
        statement = (
            select(IngestionEvent, Document.file_name, Document.status)
            .join(Document, Document.id == IngestionEvent.document_id)
            .where(IngestionEvent.user_id == user.id)
            .order_by(IngestionEvent.created_at.desc(), IngestionEvent.id.desc())
            .limit(limit)
        )
        if kb_id is not None:
            statement = statement.where(IngestionEvent.knowledge_base_id == kb_id)
        rows = (await session.execute(statement)).all()
        await session.commit()
        return _json(
            200,
            {
                "events": [
                    _serialize_event(event, file_name, document_status)
                    for event, file_name, document_status in rows
                ]
            },
        )


async def _record_uploaded(document: Document) -> None:
    await emit_event(
        document_id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        user_id=document.user_id,
        stage="uploaded",
        status="succeeded",
        message=document.file_name,
        details={
            "sizeBytes": document.size_bytes,
            "contentType": document.content_type,
            "source": document.source,
        },
    )


async def _handle_create(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    async with get_session() as session:
        user = await get_or_create_user(session, claims)
        quota = await get_quota(session, user.id)
        if await _knowledge_base_count(session, user.id) >= quota.max_knowledge_bases:
            raise ApiError(
                409,
                f"You can create at most {quota.max_knowledge_bases} knowledge bases",
            )
        description = str(body.get("description") or "").strip()
        if len(description) > MAX_DESCRIPTION_LENGTH:
            raise ApiError(
                400,
                f"Description must be at most {MAX_DESCRIPTION_LENGTH} characters",
            )
        name = _validated_kb_name(body.get("name"))
        duplicate = (
            await session.execute(
                select(KnowledgeBase.id)
                .where(
                    KnowledgeBase.user_id == user.id,
                    func.lower(KnowledgeBase.name) == name.lower(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise ApiError(409, f'A knowledge base named "{name}" already exists')
        defaults = load_config()
        chunk_size = _validated_int_range(
            body.get("chunkSize"),
            "chunkSize",
            defaults.chunk_size,
            MIN_CHUNK_SIZE,
            MAX_CHUNK_SIZE,
        )
        chunk_overlap = _validated_int_range(
            body.get("chunkOverlap"),
            "chunkOverlap",
            defaults.chunk_overlap,
            MIN_CHUNK_OVERLAP,
            MAX_CHUNK_OVERLAP,
        )
        if chunk_overlap >= chunk_size:
            raise ApiError(400, "chunkOverlap must be smaller than chunkSize")
        kb = KnowledgeBase(
            user_id=user.id,
            name=name,
            description=description or None,
            status="ready",
            embed_model=_validated_model(
                body.get("embedModel"),
                SUPPORTED_TEXT_EMBED_MODELS,
                "embedModel",
                defaults.text_embed_model,
            ),
            image_embed_model=_validated_model(
                body.get("imageEmbedModel"),
                SUPPORTED_IMAGE_EMBED_MODELS,
                "imageEmbedModel",
                defaults.image_embed_model,
            ),
            embedding_dim=defaults.embedding_dim,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        session.add(kb)
        try:
            await session.flush()
        except IntegrityError as exc:
            # The unique (user_id, lower(name)) index catches a concurrent create.
            await session.rollback()
            raise ApiError(
                409, f'A knowledge base named "{name}" already exists'
            ) from exc
        payload = _serialize_knowledge_base(kb, 0)
        await session.commit()
        return _json(201, payload)


async def _handle_detail(claims: dict[str, Any], kb_id: uuid.UUID) -> dict[str, Any]:
    async with get_session() as session:
        user = await get_or_create_user(session, claims)
        kb = (
            await session.execute(
                select(KnowledgeBase)
                .options(selectinload(KnowledgeBase.documents).selectinload(Document.tags))
                .where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user.id)
            )
        ).scalar_one_or_none()
        if kb is None:
            raise ApiError(404, "Knowledge base not found")
        documents = [
            _serialize_document(document, download_url=_presign_get(document.s3_key))
            for document in kb.documents
        ]
        await session.commit()
        return _json(
            200,
            {
                "knowledgeBase": _serialize_knowledge_base(kb, len(documents)),
                "documents": documents,
            },
        )


async def _handle_delete_kb(claims: dict[str, Any], kb_id: uuid.UUID) -> dict[str, Any]:
    async with get_session() as session:
        user = await get_or_create_user(session, claims)
        kb = await _get_knowledge_base(session, user.id, kb_id)
        # Everything for a KB lives under "{user}/{kb}/": each document's
        # original upload plus its ".derived" text/images. Delete the whole
        # prefix so no orphaned objects (or image embeddings) are left behind.
        _delete_prefix(f"{user.id}/{kb.id}/")
        await session.delete(kb)
        await session.commit()
        return _json(200, {"ok": True})


async def _handle_presign(
    claims: dict[str, Any], kb_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    async with get_session() as session:
        user = await get_or_create_user(session, claims)
        kb = await _get_knowledge_base(session, user.id, kb_id)
        quota = await get_quota(session, user.id)

        file_name = _safe_filename(str(body.get("fileName") or ""))
        if not file_name or file_name == "file":
            raise ApiError(400, "fileName is required")
        content_type = str(body.get("contentType") or "").strip() or DEFAULT_CONTENT_TYPES.get(
            _extension(file_name), "application/octet-stream"
        )
        try:
            size = int(body.get("sizeBytes") or 0)
        except (TypeError, ValueError) as exc:
            raise ApiError(400, "sizeBytes must be a number") from exc
        if size <= 0:
            raise ApiError(400, "sizeBytes must be greater than zero")
        _validate_file(file_name, content_type, size, quota)
        tags = _parse_tags(body.get("tags"))

        existing = (
            await session.execute(
                select(Document)
                .options(selectinload(Document.tags))
                .where(
                    Document.knowledge_base_id == kb.id,
                    func.lower(Document.file_name) == file_name.lower(),
                )
            )
        ).scalar_one_or_none()

        if existing is not None and existing.status != "pending":
            raise ApiError(
                409,
                f'A file named "{file_name}" already exists in this knowledge base',
            )

        if existing is not None:
            # Retry of a failed upload: reuse the pending row instead of
            # creating a duplicate.
            document = existing
            document.content_type = content_type
            document.size_bytes = size
            document.tags = _make_tags(tags)
        else:
            await _ensure_capacity(session, user.id, kb.id, quota, size)
            doc_id = uuid.uuid4()
            document = Document(
                id=doc_id,
                knowledge_base_id=kb.id,
                user_id=user.id,
                file_name=file_name,
                s3_key=_build_key(user.id, kb.id, doc_id, file_name),
                content_type=content_type,
                size_bytes=size,
                source="upload",
                status="pending",
                tags=_make_tags(tags),
            )
            session.add(document)

        await session.flush()
        key = document.s3_key
        upload_url = _presign_put(key, content_type)
        await session.commit()
        return _json(
            201,
            {
                "documentId": str(document.id),
                "key": key,
                "uploadUrl": upload_url,
                "contentType": content_type,
                "expiresIn": PRESIGN_EXPIRES_SECONDS,
            },
        )


async def _handle_complete(
    claims: dict[str, Any], kb_id: uuid.UUID, doc_id: uuid.UUID
) -> dict[str, Any]:
    async with get_session() as session:
        user = await get_or_create_user(session, claims)
        kb = await _get_knowledge_base(session, user.id, kb_id)
        quota = await get_quota(session, user.id)
        document = await _get_document(session, kb.id, doc_id)

        size = _head_object(document.s3_key)
        if size <= 0:
            raise ApiError(400, "Uploaded file was not found in storage")
        if size > quota.max_file_bytes:
            _delete_object(document.s3_key)
            await session.delete(document)
            await session.commit()
            raise ApiError(413, "File exceeds the maximum allowed size")
        used = await _user_storage_bytes(session, user.id) - document.size_bytes
        if used + size > quota.max_storage_bytes:
            _delete_object(document.s3_key)
            await session.delete(document)
            await session.commit()
            raise ApiError(413, "You have reached your storage limit")

        document.size_bytes = size
        document.content_hash = _object_etag(document.s3_key) or hashlib.sha256(
            document.s3_key.encode()
        ).hexdigest()
        document.status = "uploaded"
        payload = _serialize_document(document)
        await session.commit()
    await _record_uploaded(document)
    return _json(200, payload)


async def _handle_inline(
    claims: dict[str, Any], kb_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    async with get_session() as session:
        user = await get_or_create_user(session, claims)
        kb = await _get_knowledge_base(session, user.id, kb_id)
        quota = await get_quota(session, user.id)

        title = _validated_name(body.get("name"), "name")
        content = body.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ApiError(400, "content is required")
        data = content.encode("utf-8")
        if len(data) > quota.max_file_bytes:
            raise ApiError(413, "Content exceeds the maximum allowed size")
        await _ensure_capacity(session, user.id, kb.id, quota, len(data))
        tags = _parse_tags(body.get("tags"))

        doc_id = uuid.uuid4()
        title = re.sub(r"\.md$", "", title, flags=re.IGNORECASE).strip() or "Untitled"
        file_name = f"{_safe_filename(title)}.md"
        await _assert_unique_file_name(session, kb.id, file_name)
        key = _build_key(user.id, kb.id, doc_id, file_name)
        _put_object(key, data, "text/markdown")

        document = Document(
            id=doc_id,
            knowledge_base_id=kb.id,
            user_id=user.id,
            file_name=file_name,
            s3_key=key,
            content_type="text/markdown",
            size_bytes=len(data),
            source="inline",
            content_hash=hashlib.sha256(data).hexdigest(),
            status="uploaded",
            tags=_make_tags(tags),
        )
        session.add(document)
        await session.flush()
        payload = _serialize_document(document)
        await session.commit()
    await _record_uploaded(document)
    return _json(201, payload)


async def _handle_delete_document(
    claims: dict[str, Any], kb_id: uuid.UUID, doc_id: uuid.UUID
) -> dict[str, Any]:
    async with get_session() as session:
        user = await get_or_create_user(session, claims)
        kb = await _get_knowledge_base(session, user.id, kb_id)
        document = await _get_document(session, kb.id, doc_id)
        # Remove the original upload and the derived text/images. Deleting the
        # document row cascades to chunks, document_images and ingestion_events.
        _delete_prefix(f"{user.id}/{kb.id}/{document.id}/")
        await session.delete(document)
        await session.commit()
        return _json(200, {"ok": True})


# --- router ------------------------------------------------------------------


def _route(
    claims: dict[str, Any],
    method: str,
    segments: list[str],
    body: dict[str, Any],
    query: dict[str, str],
):
    if segments[:2] != ["v1", "knowledge-bases"]:
        raise ApiError(404, "Not found")
    rest = segments[2:]

    if not rest:
        if method == "GET":
            return _handle_list(claims)
        if method == "POST":
            return _handle_create(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 1 and rest[0] == "tags":
        if method == "GET":
            return _handle_list_tags(claims)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 1 and rest[0] == "events":
        if method == "GET":
            return _handle_list_events(claims, query)
        raise ApiError(405, f"Method not allowed: {method}")

    kb_id = _parse_uuid(rest[0], "Knowledge base")

    if len(rest) == 1:
        if method == "GET":
            return _handle_detail(claims, kb_id)
        if method == "DELETE":
            return _handle_delete_kb(claims, kb_id)
        raise ApiError(405, f"Method not allowed: {method}")

    if rest[1] != "documents":
        raise ApiError(404, "Not found")

    if len(rest) == 3:
        action = rest[2]
        if action == "presign" and method == "POST":
            return _handle_presign(claims, kb_id, body)
        if action == "inline" and method == "POST":
            return _handle_inline(claims, kb_id, body)
        if method == "DELETE":
            return _handle_delete_document(claims, kb_id, _parse_uuid(action, "Document"))
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 4:
        doc_id = _parse_uuid(rest[2], "Document")
        action = rest[3]
        if method == "POST" and action == "complete":
            return _handle_complete(claims, kb_id, doc_id)
        raise ApiError(405, f"Method not allowed: {method}")

    raise ApiError(404, "Not found")


def lambda_handler(event: dict[str, Any], _context) -> dict[str, Any]:
    claims = _claims(event)
    if not claims:
        return _json(401, {"error": "Unauthorized"})
    # Strict separation: admins must be in the user view to use this API.
    try:
        require_user(claims, event)
    except AuthError as exc:
        return _json(exc.status, {"error": exc.message})

    method = _method(event)
    try:
        coroutine = _route(
            claims, method, _segments(event), _body(event), _query(event)
        )
        return run_async(coroutine)
    except ApiError as exc:
        return _json(exc.status, {"error": exc.message})
    except ValueError as exc:
        return _json(400, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        print(f"knowledge-bases error: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        return _json(500, {"error": "Internal server error"})
