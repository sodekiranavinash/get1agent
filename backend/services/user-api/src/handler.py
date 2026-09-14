"""User-facing API Lambda.

Owns every ``/v1`` CRUD route for a signed-in user: knowledge bases and their
documents, agent skills, and account settings. Backed entirely by DynamoDB (the
single ``get1agent`` table) plus S3 for uploads/derived artifacts and the
retrieval index.
"""

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
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ai.auth import AuthError, require_user

from shared.dynamo.repositories import documents as documents_repo
from shared.dynamo.repositories import events as events_repo
from shared.dynamo.repositories import knowledge_bases as kb_repo
from shared.dynamo.repositories import settings as settings_repo
from shared.dynamo.repositories import skills as skills_repo
from shared.dynamo.repositories import tags as tags_repo
from shared.dynamo.repositories.knowledge_bases import DuplicateKnowledgeBase
from shared.dynamo.repositories.skills import DuplicateSkill
from shared.ingestion.config import (
    SUPPORTED_IMAGE_EMBED_MODELS,
    SUPPORTED_TEXT_EMBED_MODELS,
    load_config,
)
from shared.ingestion.pipeline import emit_event
from shared.json_utils import dumps as json_dumps
from shared.quotas import Quota, adjust_counters, get_quota
from shared.search import layout
from shared.search.maintenance import delete_document_index
from shared.search.s3_vectors import vector_store
from shared.skills import (
    DEFAULT_TOOLS,
    MAX_DESCRIPTION_LENGTH,
    MAX_SKILLS_PER_USER,
    MAX_SKILL_CONTENT_BYTES,
    normalize_allowed_tools,
    parse_skill_markdown,
    render_skill_markdown,
    validate_skill_name,
)
from shared.storage import Storage
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
MAX_TAGS_PER_DOCUMENT = 10

VALID_THEMES = {"light", "dark"}


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
        "body": json_dumps(body),
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


def _parse_id(value: str, label: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError) as exc:
        raise ApiError(404, f"{label} not found") from exc


# --- storage -----------------------------------------------------------------


def _storage() -> Storage:
    return Storage()


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
        raise ApiError(400, f"{label} must be between {minimum} and {maximum} tokens")
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
            raise ApiError(400, f"Tag name must be at most {MAX_TAG_NAME_LENGTH} characters")
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


# --- serialization -----------------------------------------------------------


def _serialize_document(document: dict[str, Any], *, download_url: str | None = None) -> dict[str, Any]:
    return {
        "id": document["docId"],
        "knowledgeBaseId": document["kbId"],
        "fileName": document.get("fileName"),
        "contentType": document.get("contentType"),
        "sizeBytes": document.get("sizeBytes"),
        "source": document.get("source"),
        "status": document.get("status"),
        "chunkCount": document.get("chunkCount"),
        "imageCount": document.get("imageCount"),
        "tags": list(document.get("tags") or []),
        "createdAt": document.get("createdAt"),
        "updatedAt": document.get("updatedAt"),
        "downloadUrl": download_url,
    }


def _serialize_event(
    event: dict[str, Any], file_name: str | None, document_status: str | None
) -> dict[str, Any]:
    return {
        "id": event["sk"],
        "documentId": event["documentId"],
        "knowledgeBaseId": event["knowledgeBaseId"],
        "fileName": file_name,
        "documentStatus": document_status,
        "stage": event.get("stage"),
        "status": event.get("status"),
        "message": event.get("message"),
        "details": event.get("details"),
        "createdAt": event.get("createdAt"),
    }


def _serialize_knowledge_base(kb: dict[str, Any], file_count: int) -> dict[str, Any]:
    return {
        "id": kb["kbId"],
        "name": kb.get("name"),
        "description": kb.get("description"),
        "status": kb.get("status"),
        "fileCount": file_count,
        "embedModel": kb.get("embedModel"),
        "imageEmbedModel": kb.get("imageEmbedModel"),
        "embeddingDim": kb.get("embeddingDim"),
        "chunkSize": kb.get("chunkSize"),
        "chunkOverlap": kb.get("chunkOverlap"),
        "createdAt": kb.get("createdAt"),
        "updatedAt": kb.get("updatedAt"),
    }


def _serialize_skill(skill: dict[str, Any], *, include_content: bool = False) -> dict[str, Any]:
    content = skill.get("content") or ""
    payload: dict[str, Any] = {
        "id": skill["skillId"],
        "name": skill.get("name"),
        "description": skill.get("description"),
        "allowedTools": list(skill.get("allowedTools") or []),
        "source": skill.get("source"),
        "sizeBytes": len(content.encode("utf-8")),
        "createdAt": skill.get("createdAt"),
        "updatedAt": skill.get("updatedAt"),
    }
    if include_content:
        payload["content"] = content
        payload["markdown"] = render_skill_markdown(
            skill.get("name"),
            skill.get("description"),
            skill.get("allowedTools"),
            content,
        )
    return payload


# --- knowledge bases ---------------------------------------------------------


def _get_kb_or_404(sub: str, kb_id: str) -> dict[str, Any]:
    kb = kb_repo.get_kb(sub, kb_id)
    if kb is None:
        raise ApiError(404, "Knowledge base not found")
    return kb


def _get_document_or_404(kb_id: str, doc_id: str) -> dict[str, Any]:
    document = documents_repo.get_document_by_id(doc_id)
    if document is None or document.get("kbId") != kb_id:
        raise ApiError(404, "Document not found")
    return document


def _ensure_capacity(sub: str, kb: dict[str, Any], quota: Quota, size_bytes: int) -> None:
    if int(kb.get("docCount") or 0) >= quota.max_files_per_kb:
        raise ApiError(
            409,
            f"This knowledge base already has the maximum of {quota.max_files_per_kb} files",
        )
    if quota.file_count >= quota.max_files_per_user:
        raise ApiError(409, f"You have reached the maximum of {quota.max_files_per_user} files")
    if quota.storage_bytes + size_bytes > quota.max_storage_bytes:
        raise ApiError(413, "You have reached your storage limit")


def _handle_list(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    rows = kb_repo.list_kbs(sub)
    quota = get_quota(sub)
    return _json(
        200,
        {
            "knowledgeBases": [
                _serialize_knowledge_base(kb, int(kb.get("docCount") or 0))
                for kb in rows
            ],
            "usage": {
                "knowledgeBases": len(rows),
                "files": quota.file_count,
                "storageBytes": quota.storage_bytes,
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


def _handle_list_tags(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    return _json(200, {"tags": tags_repo.list_tags(profile["userId"])})


def _handle_list_events(claims: dict[str, Any], query: dict[str, str]) -> dict[str, Any]:
    try:
        limit = min(200, max(1, int(query.get("limit", "50"))))
    except ValueError:
        limit = 50

    kb_filter = query.get("kbId")
    if kb_filter:
        try:
            kb_filter = str(uuid.UUID(kb_filter))
        except (ValueError, TypeError) as exc:
            raise ApiError(400, "Invalid kbId") from exc

    profile = get_or_create_user(claims)
    sub = profile["userId"]
    events = events_repo.list_events(sub, limit=limit, kb_id=kb_filter)

    # One BatchGet for the live document statuses referenced by the events.
    keys = []
    for event in events:
        kb_id = event.get("knowledgeBaseId")
        file_key = event.get("fileKey")
        if kb_id and file_key:
            keys.append({"pk": documents_repo.doc_pk(kb_id), "sk": file_key})
    documents = documents_repo.batch_get_documents(keys) if keys else {}

    payload = []
    for event in events:
        key = (
            documents_repo.doc_pk(event.get("knowledgeBaseId") or ""),
            event.get("fileKey") or "",
        )
        document = documents.get(key)
        payload.append(
            _serialize_event(
                event,
                (document or {}).get("fileName") or event.get("fileName"),
                (document or {}).get("status"),
            )
        )
    return _json(200, {"events": payload})


def _handle_create(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    quota = get_quota(sub)
    if quota.kb_count >= quota.max_knowledge_bases:
        raise ApiError(
            409, f"You can create at most {quota.max_knowledge_bases} knowledge bases"
        )
    description = str(body.get("description") or "").strip()
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ApiError(
            400, f"Description must be at most {MAX_DESCRIPTION_LENGTH} characters"
        )
    name = _validated_kb_name(body.get("name"))
    defaults = load_config()
    chunk_size = _validated_int_range(
        body.get("chunkSize"), "chunkSize", defaults.chunk_size, MIN_CHUNK_SIZE, MAX_CHUNK_SIZE
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

    kb_id = str(uuid.uuid4())
    try:
        kb = kb_repo.create_kb(
            sub,
            kb_id=kb_id,
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
    except DuplicateKnowledgeBase as exc:
        raise ApiError(409, f'A knowledge base named "{name}" already exists') from exc
    adjust_counters(sub, kb_count=1)
    return _json(201, _serialize_knowledge_base(kb, 0))


def _handle_detail(claims: dict[str, Any], kb_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    kb = _get_kb_or_404(sub, kb_id)
    storage = _storage()
    documents = [
        _serialize_document(document, download_url=storage.presign_get(document["s3Key"]))
        for document in documents_repo.list_documents(kb_id)
    ]
    return _json(
        200,
        {
            "knowledgeBase": _serialize_knowledge_base(kb, len(documents)),
            "documents": documents,
        },
    )


def _handle_delete_kb(claims: dict[str, Any], kb_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    kb = _get_kb_or_404(sub, kb_id)
    storage = _storage()
    store = vector_store(storage)
    documents = documents_repo.list_documents(kb_id)
    total_size = 0
    for document in documents:
        delete_document_index(storage, store, sub, document["docId"])
        tags_repo.delete_tags_for_document(document["docId"])
        events_repo.delete_events_for_document(document["docId"])
        documents_repo.delete_document(document["docId"])
        total_size += int(document.get("sizeBytes") or 0)
    storage.delete_prefix(f"{layout.RAW_PREFIX}/{sub}/{kb_id}/")
    storage.delete_prefix(f"{layout.DERIVED_PREFIX}/{sub}/{kb_id}/")
    kb_repo.delete_kb(kb_id)
    adjust_counters(
        sub,
        kb_count=-1,
        file_count=-len(documents),
        storage_bytes=-total_size,
    )
    return _json(200, {"ok": True})


def _handle_presign(
    claims: dict[str, Any], kb_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    kb = _get_kb_or_404(sub, kb_id)
    quota = get_quota(sub)
    storage = _storage()

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

    existing = documents_repo.get_document(kb_id, file_name)
    if existing is not None and existing.get("status") != "pending":
        raise ApiError(409, f'A file named "{file_name}" already exists in this knowledge base')

    if existing is not None:
        old_size = int(existing.get("sizeBytes") or 0)
        documents_repo.update_document(
            existing["docId"], contentType=content_type, sizeBytes=size
        )
        tags_repo.replace_tags(sub, existing["docId"], kb_id, existing["fileKey"], tags)
        if size != old_size:
            adjust_counters(sub, storage_bytes=size - old_size)
        document = documents_repo.get_document_by_id(existing["docId"]) or existing
    else:
        _ensure_capacity(sub, kb, quota, size)
        doc_id = str(uuid.uuid4())
        key = layout.raw_key(sub, kb_id, doc_id, file_name)
        document = documents_repo.document_item(
            doc_id=doc_id,
            kb_id=kb_id,
            user_id=sub,
            file_name=file_name,
            s3_key=key,
            content_type=content_type,
            size_bytes=size,
            source="upload",
            status="pending",
        )
        documents_repo.put_document(document, condition="attribute_not_exists(pk)")
        tags_repo.replace_tags(sub, doc_id, kb_id, document["fileKey"], tags)
        adjust_counters(sub, file_count=1, storage_bytes=size)

    upload_url = storage.presign_put(document["s3Key"], content_type, PRESIGN_EXPIRES_SECONDS)
    return _json(
        201,
        {
            "documentId": document["docId"],
            "key": document["s3Key"],
            "uploadUrl": upload_url,
            "contentType": content_type,
            "expiresIn": PRESIGN_EXPIRES_SECONDS,
        },
    )


def _handle_complete(claims: dict[str, Any], kb_id: str, doc_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    _get_kb_or_404(sub, kb_id)
    quota = get_quota(sub)
    storage = _storage()
    document = _get_document_or_404(kb_id, doc_id)

    size = storage.head_size(document["s3Key"])
    old_size = int(document.get("sizeBytes") or 0)
    if size <= 0:
        raise ApiError(400, "Uploaded file was not found in storage")
    if size > quota.max_file_bytes:
        _discard_document(sub, storage, document)
        raise ApiError(413, "File exceeds the maximum allowed size")
    used = quota.storage_bytes - old_size
    if used + size > quota.max_storage_bytes:
        _discard_document(sub, storage, document)
        raise ApiError(413, "You have reached your storage limit")

    content_hash = storage.head_etag(document["s3Key"]) or hashlib.sha256(
        document["s3Key"].encode()
    ).hexdigest()
    updated = documents_repo.update_document(
        doc_id, sizeBytes=size, contentHash=content_hash, status="uploaded"
    )
    if size != old_size:
        adjust_counters(sub, storage_bytes=size - old_size)
    payload = _serialize_document(updated or document)
    emit_event(
        document_id=doc_id,
        knowledge_base_id=kb_id,
        user_id=sub,
        stage="uploaded",
        status="succeeded",
        message=document.get("fileName"),
        details={
            "sizeBytes": size,
            "contentType": document.get("contentType"),
            "source": document.get("source"),
        },
        file_name=document.get("fileName"),
        file_key=document.get("fileKey"),
    )
    return _json(200, payload)


def _discard_document(sub: str, storage: Storage, document: dict[str, Any]) -> None:
    tags_repo.delete_tags_for_document(document["docId"])
    events_repo.delete_events_for_document(document["docId"])
    documents_repo.delete_document(document["docId"])
    storage.delete(document["s3Key"])
    adjust_counters(
        sub,
        file_count=-1,
        storage_bytes=-int(document.get("sizeBytes") or 0),
    )


def _handle_inline(claims: dict[str, Any], kb_id: str, body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    kb = _get_kb_or_404(sub, kb_id)
    quota = get_quota(sub)
    storage = _storage()

    title = _validated_name(body.get("name"), "name")
    content = body.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ApiError(400, "content is required")
    data = content.encode("utf-8")
    if len(data) > quota.max_file_bytes:
        raise ApiError(413, "Content exceeds the maximum allowed size")
    _ensure_capacity(sub, kb, quota, len(data))
    tags = _parse_tags(body.get("tags"))

    doc_id = str(uuid.uuid4())
    title = re.sub(r"\.md$", "", title, flags=re.IGNORECASE).strip() or "Untitled"
    file_name = f"{_safe_filename(title)}.md"
    if documents_repo.get_document(kb_id, file_name) is not None:
        raise ApiError(409, f'A file named "{file_name}" already exists in this knowledge base')
    key = layout.raw_key(sub, kb_id, doc_id, file_name)
    storage.put_bytes(key, data, "text/markdown")

    document = documents_repo.document_item(
        doc_id=doc_id,
        kb_id=kb_id,
        user_id=sub,
        file_name=file_name,
        s3_key=key,
        content_type="text/markdown",
        size_bytes=len(data),
        source="inline",
        status="uploaded",
        content_hash=hashlib.sha256(data).hexdigest(),
    )
    documents_repo.put_document(document, condition="attribute_not_exists(pk)")
    tags_repo.replace_tags(sub, doc_id, kb_id, document["fileKey"], tags)
    adjust_counters(sub, file_count=1, storage_bytes=len(data))
    emit_event(
        document_id=doc_id,
        knowledge_base_id=kb_id,
        user_id=sub,
        stage="uploaded",
        status="succeeded",
        message=file_name,
        details={"sizeBytes": len(data), "contentType": "text/markdown", "source": "inline"},
        file_name=file_name,
        file_key=document["fileKey"],
    )
    return _json(201, _serialize_document(document))


def _handle_delete_document(claims: dict[str, Any], kb_id: str, doc_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    _get_kb_or_404(sub, kb_id)
    document = _get_document_or_404(kb_id, doc_id)
    storage = _storage()
    store = vector_store(storage)
    delete_document_index(storage, store, sub, doc_id)
    tags_repo.delete_tags_for_document(doc_id)
    events_repo.delete_events_for_document(doc_id)
    documents_repo.delete_document(doc_id)
    storage.delete_prefix(f"{layout.RAW_PREFIX}/{sub}/{kb_id}/{doc_id}/")
    storage.delete_prefix(f"{layout.DERIVED_PREFIX}/{sub}/{kb_id}/{doc_id}/")
    adjust_counters(
        sub,
        file_count=-1,
        storage_bytes=-int(document.get("sizeBytes") or 0),
    )
    return _json(200, {"ok": True})


# --- agent skills ------------------------------------------------------------


def _validated_description(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "description is required")
    description = value.strip()
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ApiError(400, f"description must be at most {MAX_DESCRIPTION_LENGTH} characters")
    return description


def _validated_content(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "content is required")
    if len(value.encode("utf-8")) > MAX_SKILL_CONTENT_BYTES:
        raise ApiError(413, "Skill content exceeds the maximum allowed size")
    return value


def _validated_tools(value: Any) -> list[str]:
    try:
        return normalize_allowed_tools(value)
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc


def _validated_source(value: Any) -> str:
    if value in (None, ""):
        return "write"
    source = str(value).strip().lower()
    if source not in ("write", "upload"):
        raise ApiError(400, "source must be 'write' or 'upload'")
    return source


def _validated_skill_name(value: Any) -> str:
    try:
        return validate_skill_name(value)
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc


def _get_skill_or_404(sub: str, skill_id: str) -> dict[str, Any]:
    skill = skills_repo.get_skill(sub, skill_id)
    if skill is None:
        raise ApiError(404, "Skill not found")
    return skill


def _handle_skill_list(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    rows = skills_repo.list_skills(profile["userId"])
    return _json(
        200,
        {
            "skills": [_serialize_skill(skill) for skill in rows],
            "usage": {
                "skills": len(rows),
                "limits": {
                    "skills": MAX_SKILLS_PER_USER,
                    "contentBytes": MAX_SKILL_CONTENT_BYTES,
                },
            },
        },
    )


def _handle_skill_tools(claims: dict[str, Any]) -> dict[str, Any]:
    get_or_create_user(claims)
    return _json(200, {"tools": DEFAULT_TOOLS})


def _handle_skill_parse(body: dict[str, Any]) -> dict[str, Any]:
    markdown = body.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        raise ApiError(400, "markdown is required")
    return _json(200, parse_skill_markdown(markdown))


def _handle_skill_create(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    if skills_repo.count_skills(sub) >= MAX_SKILLS_PER_USER:
        raise ApiError(409, f"You can create at most {MAX_SKILLS_PER_USER} skills")
    name = _validated_skill_name(body.get("name"))
    try:
        skill = skills_repo.create_skill(
            sub,
            skill_id=str(uuid.uuid4()),
            name=name,
            description=_validated_description(body.get("description")),
            allowed_tools=_validated_tools(body.get("allowedTools")),
            content=_validated_content(body.get("content")),
            source=_validated_source(body.get("source")),
        )
    except DuplicateSkill as exc:
        raise ApiError(409, f'A skill named "{name}" already exists') from exc
    return _json(201, _serialize_skill(skill, include_content=True))


def _handle_skill_detail(claims: dict[str, Any], skill_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    skill = _get_skill_or_404(profile["userId"], skill_id)
    return _json(200, _serialize_skill(skill, include_content=True))


def _handle_skill_update(
    claims: dict[str, Any], skill_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    _get_skill_or_404(sub, skill_id)
    name = _validated_skill_name(body.get("name"))
    try:
        skill = skills_repo.update_skill(
            sub,
            skill_id,
            name=name,
            description=_validated_description(body.get("description")),
            allowed_tools=_validated_tools(body.get("allowedTools")),
            content=_validated_content(body.get("content")),
            source=_validated_source(body.get("source")),
        )
    except DuplicateSkill as exc:
        raise ApiError(409, f'A skill named "{name}" already exists') from exc
    if skill is None:
        raise ApiError(404, "Skill not found")
    return _json(200, _serialize_skill(skill, include_content=True))


def _handle_skill_delete(claims: dict[str, Any], skill_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    _get_skill_or_404(sub, skill_id)
    skills_repo.delete_skill(sub, skill_id)
    return _json(200, {"ok": True})


# --- account settings --------------------------------------------------------


def _serialize_account(
    profile: dict[str, Any], settings: dict[str, Any], prefs: dict[str, Any]
) -> dict[str, Any]:
    return {
        "id": profile["userId"],
        "email": profile.get("email"),
        "emailVerified": bool(profile.get("emailVerified", False)),
        "fullName": profile.get("fullName"),
        "pictureUrl": profile.get("pictureUrl"),
        "preferredTheme": settings.get("preferredTheme", "dark"),
        "timezone": settings.get("timezone", "UTC"),
        "emailOnWorkflowFailure": bool(prefs.get("emailOnWorkflowFailure", True)),
        "creditThresholdAlerts": bool(prefs.get("creditThresholdAlerts", True)),
    }


def _validated_full_name(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiError(400, "fullName must be a string")
    name = value.strip()
    if len(name) > 255:
        raise ApiError(400, "fullName must be at most 255 characters")
    return name or None


def _validated_theme(value: Any) -> str:
    if not isinstance(value, str) or value not in VALID_THEMES:
        raise ApiError(400, "preferredTheme must be one of: light, dark")
    return value


def _validated_timezone(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ApiError(400, "timezone must be a valid IANA timezone name")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ApiError(400, "timezone must be a valid IANA timezone name") from exc
    return value


def _validated_toggle(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ApiError(400, f"{name} must be a boolean")
    return value


def _handle_settings_get(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    settings = settings_repo.get_settings(sub)
    prefs = settings_repo.get_notification_preferences(sub)
    return _json(200, _serialize_account(profile, settings, prefs))


def _handle_settings_post(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    settings = settings_repo.get_settings(sub)
    prefs = settings_repo.get_notification_preferences(sub)

    if "fullName" in body:
        full_name = _validated_full_name(body["fullName"])
        # fullName lives on the profile row.
        from shared.dynamo.repositories import users as users_repo

        item = users_repo.get_user_by_id(sub) or profile
        item["fullName"] = full_name
        users_repo.table().put_item(Item=item)
        profile["fullName"] = full_name

    preferred_theme = (
        _validated_theme(body["preferredTheme"]) if "preferredTheme" in body else None
    )
    timezone = _validated_timezone(body["timezone"]) if "timezone" in body else None
    email_on_failure = (
        _validated_toggle("emailOnWorkflowFailure", body["emailOnWorkflowFailure"])
        if "emailOnWorkflowFailure" in body
        else None
    )
    credit_alerts = (
        _validated_toggle("creditThresholdAlerts", body["creditThresholdAlerts"])
        if "creditThresholdAlerts" in body
        else None
    )
    settings_repo.update_settings(
        sub, preferred_theme=preferred_theme, timezone=timezone
    )
    settings_repo.update_notification_preferences(
        sub,
        email_on_workflow_failure=email_on_failure,
        credit_threshold_alerts=credit_alerts,
    )
    settings = settings_repo.get_settings(sub)
    prefs = settings_repo.get_notification_preferences(sub)
    return _json(200, _serialize_account(profile, settings, prefs))


# --- router ------------------------------------------------------------------


def _route(
    claims: dict[str, Any],
    method: str,
    segments: list[str],
    body: dict[str, Any],
    query: dict[str, str],
):
    if segments[:2] == ["v1", "knowledge-bases"]:
        return _route_knowledge_bases(claims, method, segments[2:], body, query)
    if segments[:2] == ["v1", "agent-skills"]:
        return _route_agent_skills(claims, method, segments[2:], body, query)
    if segments[:3] == ["v1", "user", "settings"]:
        if method == "GET":
            return _handle_settings_get(claims)
        if method == "POST":
            return _handle_settings_post(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")
    raise ApiError(404, "Not found")


def _route_knowledge_bases(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
    query: dict[str, str],
):
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

    kb_id = _parse_id(rest[0], "Knowledge base")

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
            return _handle_delete_document(claims, kb_id, _parse_id(action, "Document"))
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 4:
        doc_id = _parse_id(rest[2], "Document")
        action = rest[3]
        if method == "POST" and action == "complete":
            return _handle_complete(claims, kb_id, doc_id)
        raise ApiError(405, f"Method not allowed: {method}")

    raise ApiError(404, "Not found")


def _route_agent_skills(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
    query: dict[str, str],
):
    if not rest:
        if method == "GET":
            return _handle_skill_list(claims)
        if method == "POST":
            return _handle_skill_create(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 1 and rest[0] == "tools":
        if method == "GET":
            return _handle_skill_tools(claims)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 1 and rest[0] == "parse":
        if method == "POST":
            return _handle_skill_parse(body)
        raise ApiError(405, f"Method not allowed: {method}")

    skill_id = _parse_id(rest[0], "Skill")
    if len(rest) == 1:
        if method == "GET":
            return _handle_skill_detail(claims, skill_id)
        if method == "PUT":
            return _handle_skill_update(claims, skill_id, body)
        if method == "DELETE":
            return _handle_skill_delete(claims, skill_id)
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
        return _route(claims, method, _segments(event), _body(event), _query(event))
    except ApiError as exc:
        return _json(exc.status, {"error": exc.message})
    except ValueError as exc:
        return _json(400, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        print(f"user-api error: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        return _json(500, {"error": "Internal server error"})
