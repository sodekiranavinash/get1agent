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

from core.auth import AuthError, require_user

from data.repositories import agents as agents_repo
from data.repositories import conversations as conversations_repo
from data.repositories import documents as documents_repo
from data.repositories import events as events_repo
from data.repositories import knowledge_bases as kb_repo
from data.repositories import mcp_connections as mcp_repo
from data.repositories import settings as settings_repo
from data.repositories import skills as skills_repo
from data.repositories import storage as storage_repo
from data.repositories import tags as tags_repo
from data.repositories.agents import DuplicateAgent
from data.repositories.knowledge_bases import DuplicateKnowledgeBase
from data.repositories.skills import DuplicateSkill
from data.repositories.knowledge_bases import list_kbs
from data.repositories.documents import get_document_by_id, update_document
from data.repositories.events import emit_event
from data.client import now_iso, table
from retrieval.embedding.config import (
    SUPPORTED_IMAGE_EMBED_MODELS,
    SUPPORTED_TEXT_EMBED_MODELS,
    load_config,
)
from core.json_utils import dumps as json_dumps
from data.repositories.quotas import Quota, adjust_counters, get_quota
from retrieval import layout
from retrieval.maintenance import delete_document_index
from retrieval.s3_vectors import vector_store
from src.skills import (
    DEFAULT_TOOLS,
    MAX_DESCRIPTION_LENGTH,
    MAX_SKILLS_PER_USER,
    MAX_SKILL_CONTENT_BYTES,
    FetchError,
    RepoError,
    catalog_entries,
    load_imported_skill,
    normalize_allowed_tools,
    parse_skill_markdown,
    render_skill_markdown,
    resolve_repo,
    search_registry,
    validate_skill_name,
)
from core.storage import Storage
from data.repositories.users import get_or_create_user, get_user_by_id

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

# Standalone storage (separate from knowledge-base quotas).
STORAGE_MAX_FILES = 10
STORAGE_MAX_FILE_BYTES = 30 * 1024 * 1024  # 30 MB per file
STORAGE_MAX_BYTES = 100 * 1024 * 1024  # 100 MB per user
MAX_NAME_LENGTH = 255
MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 1000
MAX_TAG_NAME_LENGTH = 64
MAX_TAG_DESCRIPTION_LENGTH = 500
MAX_TAGS_PER_DOCUMENT = 10

VALID_THEMES = {"light", "dark"}

# Agent builder. An agent's graph + settings live in one ``config`` map; the
# referenced KBs/skills/MCP servers are stored by id, never embedded.
MAX_AGENTS_PER_USER = 50
MAX_AGENT_CONFIG_BYTES = 256 * 1024
MAX_AGENT_PROMPT_LENGTH = 20_000
MAX_AGENT_NODES = 200
MAX_AGENT_EDGES = 400
MAX_AGENT_REFS = 50
MAX_AGENT_SERVERS = 20
MAX_AGENT_TOOLS_PER_SERVER = 100
MAX_AGENT_DEFAULT_QUESTIONS = 8
MAX_AGENT_DEFAULT_QUESTION_LENGTH = 300
SUPPORTED_AGENT_MODELS = (
    "mimo-v2.5",
    "glm-5.3-flash",
    "qwen3.8-flash",
    "deepseek-v4-flash-vision-exp",
    "gpt-5.6-luna",
    "kimi-k2.6",
)
AGENT_CONFIG_VERSION = 2
AGENT_REASONING_LEVELS = ("low", "medium", "high")
AGENT_OUTPUT_FORMATS = ("markdown", "text", "json")
BUILTIN_AGENT_SERVERS = {tool["name"] for tool in DEFAULT_TOOLS}
AGENT_NAME_MIN = 1
AGENT_NAME_MAX = 64
_AGENT_NAME_CHARS = re.compile(r"^[a-z0-9-]+$")
_AGENT_NAME_EDGES = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


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
    document = get_document_by_id(doc_id)
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


def _kb_file_count(kb: dict[str, Any]) -> int:
    """Return a KB's file count, backfilling it once for pre-counter KBs."""
    count = int(kb.get("docCount") or 0)
    if count > 0 or kb.get("docCountSynced"):
        return count
    count = len(documents_repo.list_documents(kb["kbId"]))
    kb_repo.set_doc_count(kb["kbId"], count)
    return count


def _handle_list(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    rows = list_kbs(sub)
    quota = get_quota(sub)
    return _json(
        200,
        {
            "knowledgeBases": [
                _serialize_knowledge_base(kb, _kb_file_count(kb))
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
        update_document(
            existing["docId"], contentType=content_type, sizeBytes=size
        )
        tags_repo.replace_tags(sub, existing["docId"], kb_id, existing["fileKey"], tags)
        if size != old_size:
            adjust_counters(sub, storage_bytes=size - old_size)
        document = get_document_by_id(existing["docId"]) or existing
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
        kb_repo.adjust_doc_count(kb_id, 1)

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
    updated = update_document(
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
    kb_repo.adjust_doc_count(kb_id, 1)
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
    kb_repo.adjust_doc_count(kb_id, -1)
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
    if source not in ("write", "upload", "registry"):
        raise ApiError(400, "source must be 'write', 'upload' or 'registry'")
    return source


def _validated_skill_name(value: Any) -> str:
    try:
        return validate_skill_name(value)
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc


def _sanitize_skill_name(value: Any) -> str:
    """Coerce a third-party skill name into our lowercase-hyphen format."""
    raw = str(value or "").strip().lower()
    cleaned = re.sub(r"[^a-z0-9-]+", "-", raw).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)[:64].strip("-")
    return cleaned or "imported-skill"


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


def _available_mcp_servers(user_id: str) -> list[dict[str, Any]]:
    """MCP servers a skill can be granted.

    Built-in servers are always offered; remote servers are the user's
    connected, enabled connections. Grants are per server — individual tools are
    enabled/disabled on the MCP page, so skills never reference tool names.
    """
    servers: list[dict[str, Any]] = [
        {
            "id": tool["name"],
            "name": tool.get("label") or tool["name"],
            "source": "builtin",
        }
        for tool in DEFAULT_TOOLS
    ]
    try:
        connections = mcp_repo.list_connections(user_id)
    except Exception:  # noqa: BLE001 - the editor must never break on this
        return servers
    seen = {server["id"] for server in servers}
    for connection in connections:
        if connection.get("status") != "connected":
            continue
        if connection.get("enabled") is False:
            continue
        slug = re.sub(
            r"[^a-z0-9-]+", "-", str(connection.get("name") or "").lower()
        ).strip("-")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        servers.append(
            {
                "id": slug,
                "name": str(connection.get("name") or slug),
                "source": "mcp",
            }
        )
    return servers


def _handle_skill_mcp_servers(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    return _json(200, {"servers": _available_mcp_servers(profile["userId"])})


def _handle_skill_catalog() -> dict[str, Any]:
    return _json(200, {"skills": catalog_entries()})


def _handle_skill_registry(claims: dict[str, Any], query: dict[str, str]) -> dict[str, Any]:
    return _json(200, search_registry(query))


def _handle_skill_import_preview(body: dict[str, Any]) -> dict[str, Any]:
    raw_url = str(body.get("rawUrl") or "").strip()
    if not raw_url:
        raise ApiError(400, "rawUrl is required")
    try:
        return _json(200, load_imported_skill(raw_url))
    except FetchError as exc:
        raise ApiError(400, str(exc)) from exc


def _handle_skill_resolve_repo(body: dict[str, Any]) -> dict[str, Any]:
    repo = str(body.get("repo") or "").strip()
    if not repo:
        raise ApiError(400, "repo is required")
    try:
        return _json(200, resolve_repo(repo))
    except RepoError as exc:
        raise ApiError(400, str(exc)) from exc


def _handle_skill_import(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    if skills_repo.count_skills(sub) >= MAX_SKILLS_PER_USER:
        raise ApiError(409, f"You can create at most {MAX_SKILLS_PER_USER} skills")
    raw_url = str(body.get("rawUrl") or "").strip()
    if not raw_url:
        raise ApiError(400, "rawUrl is required")
    try:
        loaded = load_imported_skill(raw_url)
    except FetchError as exc:
        raise ApiError(400, str(exc)) from exc

    name = _validated_skill_name(
        _sanitize_skill_name(body.get("name") or loaded.get("name"))
    )
    description = _validated_description(body.get("description") or loaded.get("description"))
    content = _validated_content(loaded.get("content"))
    tools = _validated_tools(body.get("allowedTools"))
    try:
        skill = skills_repo.create_skill(
            sub,
            skill_id=str(uuid.uuid4()),
            name=name,
            description=description,
            allowed_tools=tools,
            content=content,
            source="registry",
        )
    except DuplicateSkill as exc:
        raise ApiError(409, f'A skill named "{name}" already exists') from exc
    return _json(201, _serialize_skill(skill, include_content=True))


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


# --- agents ------------------------------------------------------------------


def _serialize_agent(item: dict[str, Any], *, include_config: bool = False) -> dict[str, Any]:
    config = item.get("config") or {}
    graph = config.get("graph") or {}
    payload: dict[str, Any] = {
        "id": item["agentId"],
        "name": item.get("name"),
        "description": item.get("description"),
        "status": item.get("status"),
        "visibility": item.get("visibility"),
        "source": item.get("source"),
        "version": int(item.get("version") or 1),
        "model": config.get("model"),
        "reasoning": config.get("reasoning"),
        "outputFormat": config.get("outputFormat"),
        "nodeCount": int(item.get("nodeCount") or len(graph.get("nodes") or [])),
        "defaultQuestions": list(config.get("defaultQuestions") or []),
        "knowledgeBaseCount": len(config.get("knowledgeBaseIds") or []),
        "skillCount": len(config.get("skillIds") or []),
        "serverCount": len(config.get("servers") or []),
        "schedule": config.get("schedule"),
        "verifiedAt": item.get("verifiedAt"),
        "lastRunAt": item.get("lastRunAt"),
        "publishedAt": item.get("publishedAt"),
        "installCount": int(item.get("installCount") or 0),
        "forkedFrom": item.get("forkedFrom"),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }
    if include_config:
        payload["config"] = config
    return payload


def _validated_agent_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "Agent name is required")
    name = value.strip()
    if len(name) < AGENT_NAME_MIN:
        raise ApiError(400, f"Name must be at least {AGENT_NAME_MIN} character")
    if len(name) > AGENT_NAME_MAX:
        raise ApiError(400, f"Name must be at most {AGENT_NAME_MAX} characters")
    if not _AGENT_NAME_CHARS.match(name):
        raise ApiError(
            400,
            "Name can only contain lowercase letters, numbers and hyphens "
            "(no spaces or special characters)",
        )
    if not _AGENT_NAME_EDGES.match(name):
        raise ApiError(400, "Name must start and end with a letter or number")
    return name


def _validated_agent_description(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "Agent description is required")
    description = value.strip()
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ApiError(400, f"description must be at most {MAX_DESCRIPTION_LENGTH} characters")
    return description


def _validated_enum(value: Any, allowed: tuple[str, ...], label: str, default: str) -> str:
    if value in (None, ""):
        return default
    text = str(value).strip().lower()
    if text not in allowed:
        raise ApiError(400, f"{label} must be one of {list(allowed)}")
    return text


def _validated_id_list(value: Any, label: str) -> list[str]:
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise ApiError(400, f"{label} must be a list")
    ids: list[str] = []
    seen: set[str] = set()
    for raw in value:
        try:
            item_id = str(uuid.UUID(str(raw)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ApiError(400, f"{label} contains an invalid id") from exc
        if item_id in seen:
            continue
        seen.add(item_id)
        ids.append(item_id)
    if len(ids) > MAX_AGENT_REFS:
        raise ApiError(400, f"At most {MAX_AGENT_REFS} entries are allowed in {label}")
    return ids


def _validated_agent_servers(value: Any) -> list[dict[str, Any]]:
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise ApiError(400, "servers must be a list")
    servers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in value:
        if not isinstance(entry, dict):
            raise ApiError(400, "Each server must be an object")
        server_id = str(entry.get("id") or "").strip()
        if not server_id:
            continue
        if server_id in seen:
            continue
        seen.add(server_id)
        raw_tools = entry.get("tools")
        if raw_tools is None:
            tools: list[str] | None = None
        else:
            if not isinstance(raw_tools, list):
                raise ApiError(400, "server tools must be a list")
            tools = [
                str(tool).strip()
                for tool in raw_tools
                if str(tool).strip()
            ][:MAX_AGENT_TOOLS_PER_SERVER]
        source = str(entry.get("source") or "").strip().lower()
        if source not in ("builtin", "mcp"):
            source = "builtin" if server_id in BUILTIN_AGENT_SERVERS else "mcp"
        servers.append(
            {
                "id": server_id[:128],
                "name": str(entry.get("name") or server_id)[:100],
                "source": source,
                "tools": tools,
            }
        )
    if len(servers) > MAX_AGENT_SERVERS:
        raise ApiError(400, f"At most {MAX_AGENT_SERVERS} MCP servers per agent")
    return servers


def _validated_schedule(value: Any) -> dict[str, Any]:
    if value in (None, {}):
        return {"enabled": False, "cron": "", "timezone": "UTC"}
    if not isinstance(value, dict):
        raise ApiError(400, "schedule must be an object")
    enabled = value.get("enabled")
    if not isinstance(enabled, bool):
        enabled = bool(enabled)
    cron = str(value.get("cron") or "").strip()
    timezone = str(value.get("timezone") or "UTC").strip() or "UTC"
    if len(cron) > 128:
        raise ApiError(400, "cron expression is too long")
    if enabled and not cron:
        raise ApiError(400, "A schedule needs a cron expression")
    if len(timezone) > 64:
        raise ApiError(400, "timezone must be a valid IANA timezone name")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ApiError(400, "timezone must be a valid IANA timezone name") from exc
    return {"enabled": enabled, "cron": cron, "timezone": timezone}


def _validated_graph(value: Any) -> dict[str, Any]:
    if value in (None, {}):
        return {"nodes": [], "edges": []}
    if not isinstance(value, dict):
        raise ApiError(400, "config.graph must be an object")
    nodes = value.get("nodes") or []
    edges = value.get("edges") or []
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ApiError(400, "graph nodes and edges must be lists")
    if len(nodes) > MAX_AGENT_NODES:
        raise ApiError(400, f"At most {MAX_AGENT_NODES} nodes per agent")
    if len(edges) > MAX_AGENT_EDGES:
        raise ApiError(400, f"At most {MAX_AGENT_EDGES} edges per agent")

    node_ids: set[str] = set()
    clean_nodes: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            raise ApiError(400, "Each graph node must be an object")
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            raise ApiError(400, "Every graph node needs an id")
        if node_id in node_ids:
            raise ApiError(400, f"Duplicate node id: {node_id}")
        node_ids.add(node_id)
        clean_nodes.append(node)

    clean_edges: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            raise ApiError(400, "Each graph edge must be an object")
        if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
            raise ApiError(400, "Every edge must connect two existing nodes")
        clean_edges.append(edge)

    return {"nodes": clean_nodes, "edges": clean_edges}


def _validated_agent_input(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"query": "", "fileIds": []}
    query = str(value.get("query") or "")
    if len(query) > MAX_AGENT_PROMPT_LENGTH:
        raise ApiError(400, "input.query is too long")
    return {
        "query": query,
        "fileIds": _validated_id_list(value.get("fileIds"), "input.fileIds"),
    }


def _validated_agent_output(value: Any, fallback_format: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"format": fallback_format, "instructions": ""}
    instructions = str(value.get("instructions") or "")
    if len(instructions) > MAX_AGENT_PROMPT_LENGTH:
        raise ApiError(400, "output.instructions is too long")
    return {
        "format": _validated_enum(
            value.get("format"), AGENT_OUTPUT_FORMATS, "output.format", fallback_format
        ),
        "instructions": instructions,
    }


def _validated_default_questions(value: Any) -> list[str]:
    """Optional starter questions shown on the chat screen for this agent."""
    if value in (None, []):
        return []
    if not isinstance(value, list):
        raise ApiError(400, "defaultQuestions must be a list")
    questions: list[str] = []
    for raw in value:
        text = str(raw or "").strip()
        if not text:
            continue
        if len(text) > MAX_AGENT_DEFAULT_QUESTION_LENGTH:
            raise ApiError(
                400,
                "Each default question must be at most "
                f"{MAX_AGENT_DEFAULT_QUESTION_LENGTH} characters",
            )
        questions.append(text)
        if len(questions) >= MAX_AGENT_DEFAULT_QUESTIONS:
            break
    return questions


def _validated_agent_memory(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"enabled": False}
    return {"enabled": _validated_toggle("memory.enabled", value.get("enabled", False))}


def _validated_agent_config(value: Any) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ApiError(400, "config must be an object")

    prompt = value.get("prompt")
    if prompt in (None, ""):
        prompt = ""
    elif not isinstance(prompt, str):
        raise ApiError(400, "prompt must be a string")
    elif len(prompt) > MAX_AGENT_PROMPT_LENGTH:
        raise ApiError(400, f"prompt must be at most {MAX_AGENT_PROMPT_LENGTH} characters")

    version = value.get("version")
    if not isinstance(version, int) or version < 1:
        version = AGENT_CONFIG_VERSION
    output_format = _validated_enum(
        value.get("outputFormat"), AGENT_OUTPUT_FORMATS, "outputFormat", "markdown"
    )

    config: dict[str, Any] = {
        "version": version,
        "prompt": prompt,
        "model": _validated_model(
            value.get("model"), SUPPORTED_AGENT_MODELS, "model", SUPPORTED_AGENT_MODELS[0]
        ),
        "reasoning": _validated_enum(
            value.get("reasoning"), AGENT_REASONING_LEVELS, "reasoning", "medium"
        ),
        "outputFormat": output_format,
        "input": _validated_agent_input(value.get("input")),
        "output": _validated_agent_output(value.get("output"), output_format),
        "defaultQuestions": _validated_default_questions(value.get("defaultQuestions")),
        "knowledgeBaseIds": _validated_id_list(value.get("knowledgeBaseIds"), "knowledgeBaseIds"),
        "knowledgeRerank": _validated_toggle(
            "knowledgeRerank", value.get("knowledgeRerank", False)
        ),
        "skillIds": _validated_id_list(value.get("skillIds"), "skillIds"),
        "servers": _validated_agent_servers(value.get("servers")),
        "memory": _validated_agent_memory(value.get("memory")),
        "schedule": _validated_schedule(value.get("schedule")),
        "graph": _validated_graph(value.get("graph")),
    }
    if len(json_dumps(config).encode("utf-8")) > MAX_AGENT_CONFIG_BYTES:
        raise ApiError(413, "Agent configuration is too large")
    return config


def _agent_validation(sub: str, item: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Dry-run checks: structural + every referenced entity still exists."""
    errors: list[str] = []
    warnings: list[str] = []
    config = item.get("config") or {}

    prompt = str(config.get("prompt") or "").strip()
    if not prompt:
        errors.append("The agent node needs a system prompt.")
    elif len(prompt) < 10:
        warnings.append("The system prompt is very short.")

    graph = config.get("graph") or {}
    if not any(
        isinstance(node, dict) and node.get("type") == "agent"
        for node in graph.get("nodes") or []
    ):
        errors.append("Add an agent node to the canvas.")

    for kb_id in config.get("knowledgeBaseIds") or []:
        kb = kb_repo.get_kb(sub, kb_id)
        if kb is None:
            errors.append(f"Knowledge base {kb_id} no longer exists.")
        elif kb.get("status") != "ready":
            warnings.append(f'Knowledge base "{kb.get("name")}" is still {kb.get("status")}.')

    for skill_id in config.get("skillIds") or []:
        if skills_repo.get_skill(sub, skill_id) is None:
            errors.append(f"Skill {skill_id} no longer exists.")

    for server in config.get("servers") or []:
        server_id = server.get("id")
        if server_id in BUILTIN_AGENT_SERVERS:
            continue
        connection = mcp_repo.get_connection(sub, server_id)
        if connection is None:
            errors.append(f"MCP server {server_id} is not connected.")
        elif connection.get("enabled") is False:
            errors.append(f'MCP server "{connection.get("name")}" is disabled.')
        elif connection.get("status") != "connected":
            warnings.append(
                f'MCP server "{connection.get("name")}" is {connection.get("status")}.'
            )

    schedule = config.get("schedule") or {}
    if schedule.get("enabled") and not schedule.get("cron"):
        errors.append("The schedule needs a cron expression.")

    return errors, warnings


def _get_agent_or_404(sub: str, agent_id: str) -> dict[str, Any]:
    agent = agents_repo.get_agent(sub, agent_id)
    if agent is None:
        raise ApiError(404, "Agent not found")
    return agent


def _handle_agent_list(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    rows = agents_repo.list_agents(sub)
    return _json(
        200,
        {
            "agents": [_serialize_agent(agent) for agent in rows],
            "usage": {
                "agents": len(rows),
                "limits": {"agents": MAX_AGENTS_PER_USER},
            },
        },
    )


def _handle_agent_create(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    if agents_repo.count_agents(sub) >= MAX_AGENTS_PER_USER:
        raise ApiError(409, f"You can create at most {MAX_AGENTS_PER_USER} agents")
    name = _validated_agent_name(body.get("name"))
    try:
        agent = agents_repo.create_agent(
            sub,
            agent_id=str(uuid.uuid4()),
            name=name,
            description=_validated_agent_description(body.get("description")),
            config=_validated_agent_config(body.get("config")),
        )
    except DuplicateAgent as exc:
        raise ApiError(409, f'An agent named "{name}" already exists') from exc
    return _json(201, _serialize_agent(agent, include_config=True))


def _handle_agent_detail(claims: dict[str, Any], agent_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    agent = _get_agent_or_404(profile["userId"], agent_id)
    return _json(200, _serialize_agent(agent, include_config=True))


def _handle_agent_update(
    claims: dict[str, Any], agent_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    _get_agent_or_404(sub, agent_id)
    name = _validated_agent_name(body.get("name"))
    try:
        agent = agents_repo.update_agent(
            sub,
            agent_id,
            name=name,
            description=_validated_agent_description(body.get("description")),
            config=_validated_agent_config(body.get("config")),
        )
    except DuplicateAgent as exc:
        raise ApiError(409, f'An agent named "{name}" already exists') from exc
    if agent is None:
        raise ApiError(404, "Agent not found")
    return _json(200, _serialize_agent(agent, include_config=True))


def _handle_agent_delete(claims: dict[str, Any], agent_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    _get_agent_or_404(sub, agent_id)
    agents_repo.delete_agent(sub, agent_id)
    return _json(200, {"ok": True})


def _handle_agent_verify(claims: dict[str, Any], agent_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    agent = _get_agent_or_404(sub, agent_id)
    errors, warnings = _agent_validation(sub, agent)
    if errors:
        return _json(
            200,
            {
                "valid": False,
                "errors": errors,
                "warnings": warnings,
                "agent": _serialize_agent(agent, include_config=True),
            },
        )
    status = "published" if agent.get("visibility") == "public" else "verified"
    verified_at = now_iso()
    agents_repo.mark_verified(sub, agent_id, status=status, verified_at=verified_at)
    updated = _get_agent_or_404(sub, agent_id)
    return _json(
        200,
        {
            "valid": True,
            "errors": [],
            "warnings": warnings,
            "agent": _serialize_agent(updated, include_config=True),
        },
    )


def _handle_agent_publish(claims: dict[str, Any], agent_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    agent = _get_agent_or_404(sub, agent_id)
    if not agent.get("verifiedAt"):
        raise ApiError(409, "Run a successful test before publishing this agent")
    updated = agents_repo.publish_agent(sub, agent_id, published_at=now_iso())
    if updated is None:
        raise ApiError(404, "Agent not found")
    return _json(200, _serialize_agent(updated, include_config=True))


def _handle_agent_unpublish(claims: dict[str, Any], agent_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    _get_agent_or_404(sub, agent_id)
    updated = agents_repo.unpublish_agent(sub, agent_id)
    if updated is None:
        raise ApiError(404, "Agent not found")
    return _json(200, _serialize_agent(updated, include_config=True))


def _handle_agent_library(claims: dict[str, Any], query: dict[str, str]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    try:
        limit = min(100, max(1, int(query.get("limit", "60"))))
    except ValueError:
        limit = 60
    search = str(query.get("search") or "").strip().lower()

    items, _ = agents_repo.list_library(limit=limit)
    if search:
        items = [
            item
            for item in items
            if search in str(item.get("name") or "").lower()
            or search in str(item.get("description") or "").lower()
        ]
    return _json(
        200,
        {
            "agents": [
                {**_serialize_agent(item), "isMine": item.get("userId") == sub}
                for item in items
            ],
        },
    )


def _unique_agent_name(sub: str, base: str) -> str:
    name = _validated_agent_name(base)
    if agents_repo.get_agent_by_name(sub, name) is None:
        return name
    for index in range(2, 100):
        suffix = f"-{index}"
        candidate = (name[: AGENT_NAME_MAX - len(suffix)] + suffix).strip("-")
        if candidate and agents_repo.get_agent_by_name(sub, candidate) is None:
            return candidate
    raise ApiError(409, "Could not allocate a unique agent name")


def _template_config(config: dict[str, Any]) -> dict[str, Any]:
    """A public agent's owner-scoped references do not exist for the installer."""
    clone = json.loads(json_dumps(config))
    clone["knowledgeBaseIds"] = []
    clone["skillIds"] = []
    clone["servers"] = [
        server
        for server in clone.get("servers") or []
        if server.get("source") == "builtin" or server.get("id") in BUILTIN_AGENT_SERVERS
    ]
    schedule = clone.get("schedule") or {}
    schedule["enabled"] = False
    clone["schedule"] = schedule
    return clone


def _handle_agent_install(claims: dict[str, Any], agent_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    source = agents_repo.get_public_agent(agent_id)
    if source is None:
        raise ApiError(404, "Published agent not found")
    if source.get("userId") == sub:
        raise ApiError(409, "This agent is already in your workspace")
    if agents_repo.count_agents(sub) >= MAX_AGENTS_PER_USER:
        raise ApiError(409, f"You can create at most {MAX_AGENTS_PER_USER} agents")

    name = _unique_agent_name(sub, f"{source.get('name')}-copy")
    agent = agents_repo.create_agent(
        sub,
        agent_id=str(uuid.uuid4()),
        name=name,
        description=source.get("description") or "",
        config=_template_config(source.get("config") or {}),
        source="library",
        forked_from=source.get("agentId"),
    )
    agents_repo.adjust_install_count(source, 1)
    return _json(201, _serialize_agent(agent, include_config=True))


# --- file storage (standalone) -----------------------------------------------


def _serialize_storage_file(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("fileId"),
        "fileName": item.get("fileName"),
        "contentType": item.get("contentType"),
        "sizeBytes": int(item.get("sizeBytes") or 0),
        "status": item.get("status"),
        "key": item.get("s3Key"),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }


def _storage_usage(sub: str) -> tuple[int, int]:
    """Return ``(file_count, total_bytes)`` for a user's storage files."""
    files = storage_repo.list_files(sub)
    return len(files), sum(int(item.get("sizeBytes") or 0) for item in files)


def _ensure_storage_capacity(sub: str, size_bytes: int) -> None:
    count, used = _storage_usage(sub)
    if count >= STORAGE_MAX_FILES:
        raise ApiError(409, f"You can store at most {STORAGE_MAX_FILES} files")
    if size_bytes > STORAGE_MAX_FILE_BYTES:
        raise ApiError(413, f"Each file can be at most {STORAGE_MAX_FILE_BYTES // (1024 * 1024)} MB")
    if used + size_bytes > STORAGE_MAX_BYTES:
        raise ApiError(413, "You have reached your storage limit")


def _handle_storage_list(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    files = storage_repo.list_files(sub)
    used = sum(int(item.get("sizeBytes") or 0) for item in files)
    return _json(
        200,
        {
            "files": [_serialize_storage_file(item) for item in files],
            "usage": {
                "fileCount": len(files),
                "storageBytes": used,
                "limits": {
                    "maxFiles": STORAGE_MAX_FILES,
                    "maxFileBytes": STORAGE_MAX_FILE_BYTES,
                    "maxStorageBytes": STORAGE_MAX_BYTES,
                },
            },
        },
    )


def _handle_storage_presign(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    file_name = _safe_filename(str(body.get("fileName") or ""))
    if not file_name or file_name == "file":
        raise ApiError(400, "fileName is required")
    content_type = str(body.get("contentType") or "").strip() or "application/octet-stream"
    try:
        size = int(body.get("sizeBytes") or 0)
    except (TypeError, ValueError) as exc:
        raise ApiError(400, "sizeBytes must be a number") from exc
    if size <= 0:
        raise ApiError(400, "sizeBytes must be greater than zero")
    _ensure_storage_capacity(sub, size)

    file_id = str(uuid.uuid4())
    key = layout.storage_key(sub, file_id, file_name)
    upload_url = _storage().presign_put(key, content_type, PRESIGN_EXPIRES_SECONDS)
    return _json(
        201,
        {
            "fileId": file_id,
            "key": key,
            "uploadUrl": upload_url,
            "contentType": content_type,
            "expiresIn": PRESIGN_EXPIRES_SECONDS,
        },
    )


def _handle_storage_complete(
    claims: dict[str, Any], file_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    file_id = _parse_id(file_id, "File")
    file_name = _safe_filename(str(body.get("fileName") or ""))
    if not file_name or file_name == "file":
        raise ApiError(400, "fileName is required")
    content_type = str(body.get("contentType") or "").strip() or "application/octet-stream"
    key = layout.storage_key(sub, file_id, file_name)
    storage = _storage()

    size = storage.head_size(key)
    if size <= 0:
        raise ApiError(400, "Uploaded file was not found in storage")
    _ensure_storage_capacity(sub, size)

    content_hash = storage.head_etag(key) or hashlib.sha256(key.encode()).hexdigest()
    item = storage_repo.storage_item(
        file_id=file_id,
        user_id=sub,
        file_name=file_name,
        s3_key=key,
        content_type=content_type,
        size_bytes=size,
        content_hash=content_hash,
    )
    try:
        storage_repo.put_file(item)
    except Exception as exc:  # noqa: BLE001
        storage.delete(key)
        raise ApiError(409, "This file was already uploaded") from exc
    return _json(201, _serialize_storage_file(item))


def _handle_storage_delete(claims: dict[str, Any], file_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    file_id = _parse_id(file_id, "File")
    item = storage_repo.get_file(sub, file_id)
    if item is None:
        raise ApiError(404, "File not found")
    try:
        _storage().delete(item.get("s3Key") or "")
    except Exception:  # noqa: BLE001 - deleting the row is what matters
        pass
    storage_repo.delete_file(sub, file_id)
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

        item = get_user_by_id(sub) or profile
        item["fullName"] = full_name
        table().put_item(Item=item)
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


# --- conversations -----------------------------------------------------------

MAX_CONVERSATION_TITLE = 120


def _parse_conversation_id(value: str) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ApiError(404, "Conversation not found") from exc
    if number <= 0:
        raise ApiError(404, "Conversation not found")
    return number


def _encode_cursor(key: dict[str, Any] | None) -> str | None:
    if not key:
        return None
    return base64.urlsafe_b64encode(json.dumps(key, default=str).encode()).decode()


def _decode_cursor(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        decoded = json.loads(base64.urlsafe_b64decode(value.encode()).decode())
        return decoded if isinstance(decoded, dict) else None
    except Exception:  # noqa: BLE001 - a bad cursor just restarts the page
        return None


def _serialize_conversation(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "conversationId": int(item.get("conversationId") or 0),
        "agentId": item.get("agentId"),
        "agentName": item.get("agentName"),
        "kind": item.get("kind") or conversations_repo.KIND_CHAT,
        "title": item.get("title") or "",
        "lastPreview": item.get("lastPreview") or "",
        "messageCount": int(item.get("messageCount") or 0),
        "runCount": int(item.get("runCount") or 0),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }


def _load_transcript(sub: str, conversation_id: int) -> list[dict[str, Any]]:
    data = _storage().get_json(layout.conversation_key(sub, conversation_id))
    if not isinstance(data, dict):
        return []
    turns = data.get("turns")
    return turns if isinstance(turns, list) else []


def _handle_conversation_create(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    agent_id = _parse_id(str(body.get("agentId") or ""), "Agent")
    agent = agents_repo.get_agent(sub, agent_id)
    if agent is None:
        raise ApiError(404, "Agent not found")
    kind = str(body.get("kind") or conversations_repo.KIND_CHAT).strip().lower()
    if kind not in conversations_repo.KINDS:
        raise ApiError(400, "kind must be 'chat' or 'run'")
    title = str(body.get("title") or "").strip()[:MAX_CONVERSATION_TITLE]
    item = conversations_repo.create_conversation(
        user_id=sub,
        agent_id=agent_id,
        agent_name=str(agent.get("name") or ""),
        kind=kind,
        title=title,
    )
    return _json(201, _serialize_conversation(item))


def _handle_conversation_list(
    claims: dict[str, Any], query: dict[str, str]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    try:
        limit = int(query.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(100, limit))
    cursor = _decode_cursor(query.get("cursor"))
    agent_id = str(query.get("agentId") or "").strip()
    if agent_id:
        items, next_key = conversations_repo.list_conversations_for_agent(
            sub, _parse_id(agent_id, "Agent"), limit, cursor
        )
    else:
        items, next_key = conversations_repo.list_conversations(sub, limit, cursor)
    return _json(
        200,
        {
            "conversations": [_serialize_conversation(item) for item in items],
            "nextCursor": _encode_cursor(next_key),
        },
    )


def _handle_conversation_detail(
    claims: dict[str, Any], conversation_id: int
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    item = conversations_repo.get_conversation(sub, conversation_id)
    if item is None:
        raise ApiError(404, "Conversation not found")
    return _json(
        200,
        {
            "conversation": _serialize_conversation(item),
            "turns": _load_transcript(sub, conversation_id),
        },
    )


def _handle_conversation_update(
    claims: dict[str, Any], conversation_id: int, body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    item = conversations_repo.get_conversation(sub, conversation_id)
    if item is None:
        raise ApiError(404, "Conversation not found")
    title = str(body.get("title") or "").strip()[:MAX_CONVERSATION_TITLE]
    if not title:
        raise ApiError(400, "title is required")
    updated = conversations_repo.update_conversation(sub, conversation_id, title=title)
    return _json(200, _serialize_conversation(updated or item))


def _handle_conversation_delete(
    claims: dict[str, Any], conversation_id: int
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    item = conversations_repo.delete_conversation(sub, conversation_id)
    if item is None:
        raise ApiError(404, "Conversation not found")
    try:
        _storage().delete(layout.conversation_key(sub, conversation_id))
    except Exception:  # noqa: BLE001 - removing the item is what matters
        pass
    return _json(200, {"ok": True})


def _handle_agent_runs(
    claims: dict[str, Any], agent_id: str, query: dict[str, str]
) -> dict[str, Any]:
    """List a user's conversations for one agent (builder history)."""
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    agent_id = _parse_id(agent_id, "Agent")
    if agents_repo.get_agent(sub, agent_id) is None:
        raise ApiError(404, "Agent not found")
    try:
        limit = int(query.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(100, limit))
    items, next_key = conversations_repo.list_conversations_for_agent(
        sub, agent_id, limit, _decode_cursor(query.get("cursor"))
    )
    return _json(
        200,
        {
            "runs": [_serialize_conversation(item) for item in items],
            "nextCursor": _encode_cursor(next_key),
        },
    )


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
    if segments[:2] == ["v1", "agents"]:
        return _route_agents(claims, method, segments[2:], body, query)
    if segments[:2] == ["v1", "conversations"]:
        return _route_conversations(claims, method, segments[2:], body, query)
    if segments[:2] == ["v1", "storage"]:
        return _route_storage(claims, method, segments[2:], body)
    if segments[:3] == ["v1", "user", "settings"]:
        if method == "GET":
            return _handle_settings_get(claims)
        if method == "POST":
            return _handle_settings_post(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")
    raise ApiError(404, "Not found")


def _route_conversations(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
    query: dict[str, str],
):
    if not rest:
        if method == "GET":
            return _handle_conversation_list(claims, query)
        if method == "POST":
            return _handle_conversation_create(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    conversation_id = _parse_conversation_id(rest[0])
    if len(rest) == 1:
        if method == "GET":
            return _handle_conversation_detail(claims, conversation_id)
        if method == "PATCH":
            return _handle_conversation_update(claims, conversation_id, body)
        if method == "DELETE":
            return _handle_conversation_delete(claims, conversation_id)
        raise ApiError(405, f"Method not allowed: {method}")

    raise ApiError(404, "Not found")


def _route_storage(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
):
    if rest == ["files"]:
        if method == "GET":
            return _handle_storage_list(claims)
        raise ApiError(405, f"Method not allowed: {method}")

    if rest == ["presign"]:
        if method == "POST":
            return _handle_storage_presign(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 2 and rest[0] == "files":
        if method == "DELETE":
            return _handle_storage_delete(claims, rest[1])
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 3 and rest[0] == "files" and rest[2] == "complete":
        if method == "POST":
            return _handle_storage_complete(claims, rest[1], body)
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

    if len(rest) == 1 and rest[0] == "mcp-servers":
        if method == "GET":
            return _handle_skill_mcp_servers(claims)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 1 and rest[0] == "parse":
        if method == "POST":
            return _handle_skill_parse(body)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 1 and rest[0] == "catalog":
        if method == "GET":
            return _handle_skill_catalog()
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 1 and rest[0] == "registry":
        if method == "GET":
            return _handle_skill_registry(claims, query)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 1 and rest[0] == "resolve-repo":
        if method == "POST":
            return _handle_skill_resolve_repo(body)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 1 and rest[0] == "import":
        if method == "POST":
            return _handle_skill_import(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 2 and rest[0] == "import" and rest[1] == "preview":
        if method == "POST":
            return _handle_skill_import_preview(body)
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


def _route_agents(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
    query: dict[str, str],
):
    if not rest:
        if method == "GET":
            return _handle_agent_list(claims)
        if method == "POST":
            return _handle_agent_create(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    # The public library is a static segment and must be matched before ids.
    if rest[0] == "library":
        if len(rest) == 1:
            if method == "GET":
                return _handle_agent_library(claims, query)
            raise ApiError(405, f"Method not allowed: {method}")
        if len(rest) == 3 and rest[2] == "install":
            if method == "POST":
                return _handle_agent_install(claims, _parse_id(rest[1], "Agent"))
            raise ApiError(405, f"Method not allowed: {method}")
        raise ApiError(404, "Not found")

    agent_id = _parse_id(rest[0], "Agent")

    if len(rest) == 1:
        if method == "GET":
            return _handle_agent_detail(claims, agent_id)
        if method == "PUT":
            return _handle_agent_update(claims, agent_id, body)
        if method == "DELETE":
            return _handle_agent_delete(claims, agent_id)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 2:
        action = rest[1]
        if method == "GET" and action == "runs":
            return _handle_agent_runs(claims, agent_id, query)
        if method == "POST" and action == "verify":
            return _handle_agent_verify(claims, agent_id)
        if method == "POST" and action == "publish":
            return _handle_agent_publish(claims, agent_id)
        if method == "POST" and action == "unpublish":
            return _handle_agent_unpublish(claims, agent_id)
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
