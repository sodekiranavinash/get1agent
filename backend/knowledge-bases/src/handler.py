import base64
import hashlib
import json
import os
import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from shared.db.engine import run_async
from shared.db.session import get_session
from shared.models import Document, DocumentTag, KnowledgeBase
from shared.models.document_tag import MAX_TAGS_PER_DOCUMENT, MIN_TAG_DESCRIPTION_LENGTH
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


def _parse_uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError) as exc:
        raise ApiError(404, f"{label} not found") from exc


# --- storage -----------------------------------------------------------------


def _bucket() -> str | None:
    return os.environ.get("S3_BUCKET") or None


def _storage_mode() -> str:
    return "s3" if _bucket() else "local"


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


def _local_root() -> str:
    return os.environ.get("LOCAL_STORAGE_DIR", "local/.storage")


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
    if _storage_mode() != "s3":
        return None
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": key},
        ExpiresIn=PRESIGN_EXPIRES_SECONDS,
    )


def _put_object(key: str, data: bytes, content_type: str) -> None:
    if _storage_mode() == "s3":
        _s3_client().put_object(
            Bucket=_bucket(), Key=key, Body=data, ContentType=content_type
        )
        return
    path = os.path.join(_local_root(), key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def _head_object(key: str) -> int:
    if _storage_mode() == "s3":
        response = _s3_client().head_object(Bucket=_bucket(), Key=key)
        return int(response["ContentLength"])
    path = os.path.join(_local_root(), key)
    return os.path.getsize(path) if os.path.exists(path) else 0


def _delete_object(key: str) -> None:
    if _storage_mode() == "s3":
        _s3_client().delete_object(Bucket=_bucket(), Key=key)
        return
    path = os.path.join(_local_root(), key)
    if os.path.exists(path):
        os.remove(path)


# --- validation --------------------------------------------------------------


def _validated_name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, f"{label} is required")
    name = value.strip()
    if len(name) > MAX_NAME_LENGTH:
        raise ApiError(400, f"{label} must be at most {MAX_NAME_LENGTH} characters")
    return name


def _parse_tags(raw: Any) -> list[tuple[str, str]]:
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise ApiError(400, "tags must be a list")
    if len(raw) > MAX_TAGS_PER_DOCUMENT:
        raise ApiError(400, f"At most {MAX_TAGS_PER_DOCUMENT} tags per file")
    tags: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ApiError(400, "Each tag must be an object with name and description")
        name = str(item.get("name") or "").strip()
        description = str(item.get("description") or "").strip()
        if not name or len(name) > 64:
            raise ApiError(400, "Tag name is required and must be at most 64 characters")
        if len(description) < MIN_TAG_DESCRIPTION_LENGTH:
            raise ApiError(
                400,
                f"Tag description must be at least {MIN_TAG_DESCRIPTION_LENGTH} characters",
            )
        if name.lower() in seen:
            raise ApiError(400, f"Duplicate tag: {name}")
        seen.add(name.lower())
        tags.append((name, description))
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
        "tags": [
            {"name": tag.name, "description": tag.description} for tag in document.tags
        ],
        "createdAt": _iso(document.created_at),
        "updatedAt": _iso(document.updated_at),
        "downloadUrl": download_url,
    }


def _serialize_knowledge_base(kb: KnowledgeBase, file_count: int) -> dict[str, Any]:
    return {
        "id": str(kb.id),
        "name": kb.name,
        "description": kb.description,
        "status": kb.status,
        "fileCount": file_count,
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


async def _ensure_capacity(session, kb_id: uuid.UUID, quota: Quota) -> None:
    if await _document_count(session, kb_id) >= quota.max_files_per_kb:
        raise ApiError(
            409,
            f"This knowledge base already has the maximum of {quota.max_files_per_kb} files",
        )


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
        await session.commit()
        return _json(
            200,
            {"knowledgeBases": [_serialize_knowledge_base(kb, count) for kb, count in rows]},
        )


async def _handle_create(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    async with get_session() as session:
        user = await get_or_create_user(session, claims)
        kb = KnowledgeBase(
            user_id=user.id,
            name=_validated_name(body.get("name"), "name"),
            description=(str(body["description"]).strip() or None)
            if body.get("description")
            else None,
            status="ready",
        )
        session.add(kb)
        await session.flush()
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
        keys = (
            await session.execute(select(Document.s3_key).where(Document.knowledge_base_id == kb.id))
        ).scalars().all()
        for key in keys:
            _delete_object(key)
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
        await _ensure_capacity(session, kb.id, quota)

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

        doc_id = uuid.uuid4()
        key = _build_key(user.id, kb.id, doc_id, file_name)
        document = Document(
            id=doc_id,
            knowledge_base_id=kb.id,
            user_id=user.id,
            file_name=file_name,
            s3_key=key,
            content_type=content_type,
            size_bytes=size,
            source="upload",
            status="pending",
            tags=_make_tags(tags),
        )
        session.add(document)
        await session.flush()

        mode = _storage_mode()
        upload_url = _presign_put(key, content_type) if mode == "s3" else None
        await session.commit()
        return _json(
            201,
            {
                "documentId": str(doc_id),
                "key": key,
                "mode": mode,
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

        document.size_bytes = size
        document.content_hash = hashlib.sha256(document.s3_key.encode()).hexdigest()
        document.status = "uploaded"
        payload = _serialize_document(document)
        await session.commit()
        return _json(200, payload)


async def _handle_local_upload(
    claims: dict[str, Any], kb_id: uuid.UUID, doc_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    if _storage_mode() != "local":
        raise ApiError(403, "Direct upload is only available in local mode")
    raw = body.get("contentBase64")
    if not isinstance(raw, str) or not raw:
        raise ApiError(400, "contentBase64 is required")
    try:
        data = base64.b64decode(raw)
    except (ValueError, TypeError) as exc:
        raise ApiError(400, "contentBase64 is not valid base64") from exc

    async with get_session() as session:
        user = await get_or_create_user(session, claims)
        kb = await _get_knowledge_base(session, user.id, kb_id)
        quota = await get_quota(session, user.id)
        document = await _get_document(session, kb.id, doc_id)
        if len(data) > quota.max_file_bytes:
            await session.delete(document)
            await session.commit()
            raise ApiError(413, "File exceeds the maximum allowed size")

        _put_object(document.s3_key, data, document.content_type or "application/octet-stream")
        document.size_bytes = len(data)
        document.content_hash = hashlib.sha256(data).hexdigest()
        document.status = "uploaded"
        payload = _serialize_document(document)
        await session.commit()
        return _json(200, payload)


async def _handle_inline(
    claims: dict[str, Any], kb_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    async with get_session() as session:
        user = await get_or_create_user(session, claims)
        kb = await _get_knowledge_base(session, user.id, kb_id)
        quota = await get_quota(session, user.id)
        await _ensure_capacity(session, kb.id, quota)

        title = _validated_name(body.get("name"), "name")
        content = body.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ApiError(400, "content is required")
        data = content.encode("utf-8")
        if len(data) > quota.max_file_bytes:
            raise ApiError(413, "Content exceeds the maximum allowed size")
        tags = _parse_tags(body.get("tags"))

        doc_id = uuid.uuid4()
        file_name = f"{_safe_filename(title)}.md"
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
        return _json(201, payload)


async def _handle_delete_document(
    claims: dict[str, Any], kb_id: uuid.UUID, doc_id: uuid.UUID
) -> dict[str, Any]:
    async with get_session() as session:
        user = await get_or_create_user(session, claims)
        kb = await _get_knowledge_base(session, user.id, kb_id)
        document = await _get_document(session, kb.id, doc_id)
        _delete_object(document.s3_key)
        await session.delete(document)
        await session.commit()
        return _json(200, {"ok": True})


# --- router ------------------------------------------------------------------


def _route(claims: dict[str, Any], method: str, segments: list[str], body: dict[str, Any]):
    if segments[:2] != ["v1", "knowledge-bases"]:
        raise ApiError(404, "Not found")
    rest = segments[2:]

    if not rest:
        if method == "GET":
            return _handle_list(claims)
        if method == "POST":
            return _handle_create(claims, body)
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
        if method == "POST" and action == "upload":
            return _handle_local_upload(claims, kb_id, doc_id, body)
        raise ApiError(405, f"Method not allowed: {method}")

    raise ApiError(404, "Not found")


def lambda_handler(event: dict[str, Any], _context) -> dict[str, Any]:
    claims = _claims(event)
    if not claims:
        return _json(401, {"error": "Unauthorized"})

    method = _method(event)
    try:
        coroutine = _route(claims, method, _segments(event), _body(event))
        return run_async(coroutine)
    except ApiError as exc:
        return _json(exc.status, {"error": exc.message})
    except ValueError as exc:
        return _json(400, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        print(f"knowledge-bases error: {exc}")
        return _json(500, {"error": "Internal server error"})
