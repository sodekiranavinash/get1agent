"""User-facing API Lambda.

Owns every ``/v1`` CRUD route for a signed-in user: knowledge bases and their
documents, agent skills, and account settings. Backed entirely by DynamoDB (the
single ``get1agent`` table) plus S3 for uploads/derived artifacts and the
retrieval index.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.auth import AuthError, require_user

from data.repositories import agents as agents_repo
from data.repositories import consent as consent_repo
from data.repositories import conversations as conversations_repo
from data.repositories import custom_tools as custom_tools_repo
from data.repositories import documents as documents_repo
from data.repositories import evals as evals_repo
from data.repositories import events as events_repo
from data.repositories import feedback as feedback_repo
from data.repositories import guardrails as guardrails_repo
from data.repositories import knowledge_bases as kb_repo
from data.repositories import mcp_connections as mcp_repo
from data.repositories import notifications as notifications_repo
from data.repositories import playground as playground_repo
from data.repositories import schedules as schedules_repo
from data.repositories import settings as settings_repo
from data.repositories import skills as skills_repo
from data.repositories import storage as storage_repo
from data.repositories import support as support_repo
from data.repositories import tags as tags_repo
from data.repositories import vault as vault_repo
from data.repositories import workflows as workflows_repo
from data.repositories.agents import DuplicateAgent
from data.repositories.custom_tools import DuplicateCustomServer, DuplicateCustomTool
from data.repositories.knowledge_bases import DuplicateKnowledgeBase
from data.repositories.guardrails import DuplicateGuardrail
from data.repositories.skills import DuplicateSkill
from data.repositories.vault import DuplicateVaultSecret
from data.repositories.workflows import DuplicateWorkflow
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
from data.repositories.quotas import (
    BudgetExceeded,
    Quota,
    adjust_counters,
    charge_usage,
    check_budget,
    get_budget,
    get_quota,
)
from retrieval import layout
from retrieval.maintenance import delete_document_index
from retrieval.s3_vectors import vector_store
from src.custom_tools import (
    CUSTOM_TOOL_ENTRYPOINT,
    GenerationError,
    MAX_CUSTOM_SERVERS_PER_USER,
    MAX_CUSTOM_TOOL_CODE_BYTES,
    MAX_CUSTOM_TOOLS_PER_SERVER,
    async_timeout,
    generate_tool,
    normalize_schema,
    slugify as custom_slugify,
    validate_code,
    validate_description as validate_custom_description,
    validate_server_name,
    validate_tool_name,
)
from src.evals import config as evals_config
from src.evals import judge as evals_judge
from src.evals import store as lab_store
from src.evals import playground as evals_playground
from src.evals import runner as evals_runner
from src.vault import (
    TestError as VaultTestError,
    get_provider as get_vault_provider,
    list_models as list_vault_models,
    provider_public_list as vault_provider_list,
    test_provider as test_vault_provider,
)
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
from core import usage as core_usage
from core.storage import Storage
from data.repositories.users import (
    delete_identity,
    delete_user_data,
    get_or_create_user,
    get_user_by_id,
)

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

# Vault: encrypted user secrets. Values are KMS direct-encrypted, so the whole
# secret payload must stay under KMS' 4096-byte plaintext cap.
MAX_VAULT_SECRETS = 100
MAX_VAULT_NAME_LENGTH = 64
MAX_VAULT_LABEL_LENGTH = 120
MAX_VAULT_DESCRIPTION_LENGTH = 500
MAX_VAULT_BASE_URL_LENGTH = 500
MAX_VAULT_MODEL_LENGTH = 200
MAX_VAULT_MODELS = 20
# KMS direct-encrypt caps the plaintext at 4096 bytes; the sealed payload is
# ``{"fields": {...}}`` JSON, measured exactly below.
VAULT_PAYLOAD_LIMIT_BYTES = 4096
_VAULT_NAME_CHARS = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_VAULT_NAME_EDGES = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
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

# Workflows compose saved agents. One item per workflow; the config holds the
# mode (graph | swarm), the input/output settings and the node/edge graph. Agent
# nodes reference saved agents by id and may override a few fields per workflow.
MAX_WORKFLOWS_PER_USER = 50
MAX_WORKFLOW_CONFIG_BYTES = 256 * 1024
MAX_WORKFLOW_NODES = 100
MAX_WORKFLOW_EDGES = 300
# Up to ten agents per workflow, so the builder's agent column always fits.
MAX_WORKFLOW_AGENTS = 10
WORKFLOW_CONFIG_VERSION = 1
WORKFLOW_MODES = ("graph", "swarm")
WORKFLOW_NODE_KINDS = ("input", "agent", "output", "schedule")
SUPPORTED_AGENT_MODELS = (
    "zai.glm-4.7-flash",
    "nvidia.nemotron-nano-3-30b",
    "deepseek.v3.2",
    "qwen.qwen3-next-80b-a3b",
    "global.amazon.nova-2-lite-v1:0",
)
AGENT_CONFIG_VERSION = 4
AGENT_REASONING_LEVELS = ("low", "medium", "high")
AGENT_OUTPUT_FORMATS = ("markdown", "text", "json")
# How detailed an agent's answer should be. `summarize` is the default.
AGENT_ANSWER_MODES = ("summarize", "normal", "detailed")
BUILTIN_AGENT_SERVERS = {tool["name"] for tool in DEFAULT_TOOLS}
AGENT_NAME_MIN = 1
AGENT_NAME_MAX = 64
_AGENT_NAME_CHARS = re.compile(r"^[a-z0-9-]+$")
_AGENT_NAME_EDGES = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")

# Bedrock guardrails a user creates from the app. One item per guardrail, plus
# the workspace default recorded on the settings item.
MAX_GUARDRAILS_PER_USER = 20
GUARDRAIL_NAME_MIN = 1
GUARDRAIL_NAME_MAX = 48
MAX_GUARDRAIL_DESCRIPTION_LENGTH = 200
MAX_GUARDRAIL_TOPICS = 30
MAX_GUARDRAIL_TOPIC_NAME = 100
MAX_GUARDRAIL_TOPIC_DEFINITION = 200
MAX_GUARDRAIL_WORDS = 10000
MAX_GUARDRAIL_REGEXES = 10
# Reserved route segments that must never collide with a guardrail name.
_GUARDRAIL_RESERVED = {"config", "test"}


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


def _require_budget(claims: dict[str, Any]) -> str:
    """Gate a route that spends the platform LLM key; returns the internal userId.

    Admins are not special-cased — they start on the same default grant and an
    admin raises it (or sets the ``unlimited`` override) explicitly. Raises
    ``402`` when the user's application budget is exhausted.
    """
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    try:
        check_budget(sub)
    except BudgetExceeded as exc:
        raise ApiError(402, str(exc)) from exc
    return sub


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
    seen = {server["id"] for server in servers}

    # The user's own Python tools (Playground) are grantable too.
    try:
        for custom in custom_tools_repo.list_servers(user_id):
            slug = str(custom.get("slug") or "")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            servers.append(
                {
                    "id": slug,
                    "name": str(custom.get("name") or slug),
                    "source": "custom",
                }
            )
    except Exception:  # noqa: BLE001 - the editor must never break on this
        pass

    try:
        connections = mcp_repo.list_connections(user_id)
    except Exception:  # noqa: BLE001 - the editor must never break on this
        return servers
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


# --- custom tools (Playground) -----------------------------------------------


def _custom_code_prefix(sub: str, slug: str) -> str:
    return f"{layout.CUSTOM_PREFIX}/{sub}/{slug}/"


def _read_custom_code(item: dict[str, Any]) -> str:
    """Best-effort read of a tool's source from S3 (empty when unavailable)."""
    key = str(item.get("codeKey") or "")
    if not key:
        return ""
    try:
        return _storage().get_bytes(key).decode("utf-8")
    except Exception:  # noqa: BLE001 - a missing object must not break the editor
        return ""


def _serialize_custom_tool(
    item: dict[str, Any], *, code: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": item["toolId"],
        "serverId": item.get("serverId"),
        "name": item.get("name"),
        "description": item.get("description") or "",
        "inputSchema": item.get("inputSchema") or {"type": "object", "properties": {}},
        "outputSchema": item.get("outputSchema")
        or {"type": "object", "properties": {}},
        "entrypoint": item.get("entrypoint") or CUSTOM_TOOL_ENTRYPOINT,
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }
    if code is not None:
        payload["code"] = code
    return payload


def _serialize_custom_server(
    item: dict[str, Any], tools: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "id": item["serverId"],
        "name": item.get("name"),
        "slug": item.get("slug"),
        "description": item.get("description") or "",
        "toolCount": len(tools),
        "tools": tools,
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }


def _get_custom_server_or_404(sub: str, server_id: str) -> dict[str, Any]:
    server = custom_tools_repo.get_server(sub, server_id)
    if server is None:
        raise ApiError(404, "Custom tool server not found")
    return server


def _handle_custom_tools_list(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    servers = custom_tools_repo.list_servers(sub)
    # One query for every tool, grouped in memory (never N+1 per server).
    by_slug: dict[str, list[dict[str, Any]]] = {}
    for tool in custom_tools_repo.list_all_tools(sub):
        by_slug.setdefault(str(tool.get("serverSlug") or ""), []).append(tool)
    payload = [
        _serialize_custom_server(
            server,
            [
                _serialize_custom_tool(tool)
                for tool in sorted(
                    by_slug.get(str(server.get("slug") or ""), []),
                    key=lambda item: item.get("name", ""),
                )
            ],
        )
        for server in servers
    ]
    return _json(
        200,
        {
            "servers": payload,
            "usage": {
                "servers": len(servers),
                "tools": sum(len(tools) for tools in by_slug.values()),
                "limits": {
                    "servers": MAX_CUSTOM_SERVERS_PER_USER,
                    "toolsPerServer": MAX_CUSTOM_TOOLS_PER_SERVER,
                    "codeBytes": MAX_CUSTOM_TOOL_CODE_BYTES,
                },
            },
        },
    )


def _handle_custom_tools_create(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    if custom_tools_repo.count_servers(sub) >= MAX_CUSTOM_SERVERS_PER_USER:
        raise ApiError(409, f"You can create at most {MAX_CUSTOM_SERVERS_PER_USER} servers")
    try:
        name = validate_server_name(body.get("name"))
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc
    slug = custom_slugify(name)
    if not slug:
        raise ApiError(400, "Name must contain at least one letter or number")
    try:
        server = custom_tools_repo.create_server(
            sub,
            server_id=str(uuid.uuid4()),
            name=name,
            slug=slug,
            description=validate_custom_description(body.get("description")),
        )
    except DuplicateCustomServer as exc:
        raise ApiError(409, f'A server named "{name}" already exists') from exc
    return _json(201, _serialize_custom_server(server, []))


def _handle_custom_tools_detail(claims: dict[str, Any], server_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    server = _get_custom_server_or_404(sub, server_id)
    tools = custom_tools_repo.list_tools(sub, str(server.get("slug") or ""))
    serialized = [
        _serialize_custom_tool(tool, code=_read_custom_code(tool)) for tool in tools
    ]
    return _json(200, _serialize_custom_server(server, serialized))


def _handle_custom_tools_update(
    claims: dict[str, Any], server_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    existing = _get_custom_server_or_404(sub, server_id)
    try:
        name = validate_server_name(body.get("name") or existing.get("name"))
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc
    # The slug (and therefore the tool namespace) is immutable.
    slug = str(existing.get("slug") or "")
    try:
        server = custom_tools_repo.update_server(
            sub,
            server_id,
            name=name,
            slug=slug,
            description=validate_custom_description(body.get("description")),
        )
    except DuplicateCustomServer as exc:
        raise ApiError(409, f'A server named "{name}" already exists') from exc
    if server is None:
        raise ApiError(404, "Custom tool server not found")
    tools = custom_tools_repo.list_tools(sub, slug)
    return _json(200, _serialize_custom_server(server, [_serialize_custom_tool(t) for t in tools]))


def _handle_custom_tools_delete(claims: dict[str, Any], server_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    server = _get_custom_server_or_404(sub, server_id)
    slug = str(server.get("slug") or "")
    custom_tools_repo.delete_server(sub, server_id)
    try:
        _storage().delete_prefix(_custom_code_prefix(sub, slug))
    except Exception:  # noqa: BLE001 - best effort cleanup
        pass
    return _json(200, {"ok": True})


def _validated_custom_tool_body(body: dict[str, Any]) -> dict[str, Any]:
    try:
        name = validate_tool_name(body.get("name"))
        code = validate_code(body.get("code"))
        input_schema = normalize_schema(body.get("inputSchema"))
        output_schema = normalize_schema(body.get("outputSchema"))
        description = validate_custom_description(body.get("description"))
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc
    entrypoint = str(body.get("entrypoint") or CUSTOM_TOOL_ENTRYPOINT).strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", entrypoint):
        raise ApiError(400, "entrypoint must be a valid Python function name")
    return {
        "name": name,
        "code": code,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "description": description,
        "entrypoint": entrypoint,
    }


def _handle_custom_tool_create(
    claims: dict[str, Any], server_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    server = _get_custom_server_or_404(sub, server_id)
    slug = str(server.get("slug") or "")
    if custom_tools_repo.count_tools(sub) >= MAX_CUSTOM_SERVERS_PER_USER * MAX_CUSTOM_TOOLS_PER_SERVER:
        raise ApiError(409, "Too many custom tools")
    if len(custom_tools_repo.list_tools(sub, slug)) >= MAX_CUSTOM_TOOLS_PER_SERVER:
        raise ApiError(409, f"At most {MAX_CUSTOM_TOOLS_PER_SERVER} tools per server")
    fields = _validated_custom_tool_body(body)
    code_key = layout.custom_tool_key(sub, slug, fields["name"])
    _storage().put_bytes(code_key, fields["code"].encode("utf-8"), "text/x-python")
    try:
        tool = custom_tools_repo.create_tool(
            sub,
            tool_id=str(uuid.uuid4()),
            server_id=server_id,
            server_slug=slug,
            name=fields["name"],
            description=fields["description"],
            input_schema=fields["input_schema"],
            output_schema=fields["output_schema"],
            code_key=code_key,
            code_hash=hashlib.sha256(fields["code"].encode("utf-8")).hexdigest(),
            entrypoint=fields["entrypoint"],
        )
    except DuplicateCustomTool as exc:
        raise ApiError(409, f'A tool named "{fields["name"]}" already exists') from exc
    return _json(201, _serialize_custom_tool(tool, code=fields["code"]))


def _handle_custom_tool_detail(
    claims: dict[str, Any], server_id: str, tool_id: str
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    server = _get_custom_server_or_404(sub, server_id)
    tool = custom_tools_repo.get_tool(sub, tool_id)
    if tool is None or tool.get("serverId") != server_id:
        raise ApiError(404, "Custom tool not found")
    return _json(200, _serialize_custom_tool(tool, code=_read_custom_code(tool)))


def _handle_custom_tool_update(
    claims: dict[str, Any], server_id: str, tool_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    server = _get_custom_server_or_404(sub, server_id)
    slug = str(server.get("slug") or "")
    existing = custom_tools_repo.get_tool(sub, tool_id)
    if existing is None or existing.get("serverId") != server_id:
        raise ApiError(404, "Custom tool not found")
    fields = _validated_custom_tool_body(body)
    code_key = layout.custom_tool_key(sub, slug, fields["name"])
    _storage().put_bytes(code_key, fields["code"].encode("utf-8"), "text/x-python")
    old_key = str(existing.get("codeKey") or "")
    if old_key and old_key != code_key:
        try:
            _storage().delete(old_key)
        except Exception:  # noqa: BLE001 - best effort
            pass
    try:
        tool = custom_tools_repo.update_tool(
            sub,
            tool_id,
            server_id=server_id,
            server_slug=slug,
            name=fields["name"],
            description=fields["description"],
            input_schema=fields["input_schema"],
            output_schema=fields["output_schema"],
            code_key=code_key,
            code_hash=hashlib.sha256(fields["code"].encode("utf-8")).hexdigest(),
            entrypoint=fields["entrypoint"],
        )
    except DuplicateCustomTool as exc:
        raise ApiError(409, f'A tool named "{fields["name"]}" already exists') from exc
    if tool is None:
        raise ApiError(404, "Custom tool not found")
    return _json(200, _serialize_custom_tool(tool, code=fields["code"]))


def _handle_custom_tool_delete(
    claims: dict[str, Any], server_id: str, tool_id: str
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    _get_custom_server_or_404(sub, server_id)
    existing = custom_tools_repo.get_tool(sub, tool_id)
    if existing is None or existing.get("serverId") != server_id:
        raise ApiError(404, "Custom tool not found")
    custom_tools_repo.delete_tool(sub, tool_id)
    key = str(existing.get("codeKey") or "")
    if key:
        try:
            _storage().delete(key)
        except Exception:  # noqa: BLE001 - best effort
            pass
    return _json(200, {"ok": True})


def _custom_tools_function() -> str:
    return os.environ.get("CUSTOM_TOOLS_FUNCTION", "").strip()


def _invoke_custom_tools(payload: dict[str, Any]) -> dict[str, Any]:
    """Direct-invoke the custom-tools Lambda (IAM-trusted, no HTTP timeout)."""
    function = _custom_tools_function()
    if not function:
        raise ApiError(500, "Custom tool execution is not configured")
    import boto3

    client = boto3.client("lambda", region_name=os.environ.get("AWS_REGION"))
    response = client.invoke(
        FunctionName=function,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    raw = response["Payload"].read()
    if response.get("FunctionError"):
        raise ApiError(502, "Tool execution failed")
    try:
        parsed = json.loads(raw or b"{}")
    except ValueError as exc:
        raise ApiError(502, "Tool execution returned an invalid response") from exc
    return parsed if isinstance(parsed, dict) else {}


# --- background jobs (async Lambda invocations) ------------------------------
#
# API Gateway caps a synchronous integration at 30s. Playground code generation
# can exceed that (a reasoning model re-emits the entire tool as JSON), so the
# turn route persists a "generating" placeholder and starts the work as a
# background invocation of this same function, which may run up to the Lambda
# timeout. The client polls the session until the placeholder resolves.

_ASYNC_ACTION = "__userApiAsync"


def _self_function_name() -> str:
    return (
        os.environ.get("USER_API_FUNCTION_NAME")
        or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
        or ""
    ).strip()


def _invoke_self_async(payload: dict[str, Any]) -> None:
    """Fire-and-forget background invocation of this Lambda."""
    function = _self_function_name()
    if not function:
        raise ApiError(500, "Background generation is not configured")
    import boto3

    client = boto3.client("lambda", region_name=os.environ.get("AWS_REGION"))
    client.invoke(
        FunctionName=function,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8"),
    )


def _run_async_job(event: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a background invocation. Never raises: an unhandled error would
    make Lambda retry an ``Event`` invocation and duplicate the work."""
    try:
        action = event.get(_ASYNC_ACTION)
        if action == "playground.generate":
            return _run_playground_generate_job(event)
        if action == "evals.run":
            return _run_evals_job(event)
        raise ValueError(f"Unknown background action: {action}")
    except Exception as exc:  # noqa: BLE001
        print(f"user-api background job failed: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        return {"ok": False, "error": "background job failed"}


def _handle_custom_tools_test(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    args = body.get("args")
    if not isinstance(args, dict):
        args = {}

    tool_id = str(body.get("toolId") or "").strip()
    if tool_id:
        tool = custom_tools_repo.get_tool(sub, tool_id)
        if tool is None:
            raise ApiError(404, "Custom tool not found")
        code = _read_custom_code(tool)
        input_schema = tool.get("inputSchema")
        output_schema = tool.get("outputSchema")
        entrypoint = str(tool.get("entrypoint") or CUSTOM_TOOL_ENTRYPOINT)
    else:
        try:
            code = validate_code(body.get("code"))
            input_schema = normalize_schema(body.get("inputSchema"))
            output_schema = normalize_schema(body.get("outputSchema"))
        except ValueError as exc:
            raise ApiError(400, str(exc)) from exc
        entrypoint = str(body.get("entrypoint") or CUSTOM_TOOL_ENTRYPOINT).strip()

    result = _invoke_custom_tools(
        {
            "action": "test",
            "userId": sub,
            "code": code,
            "args": args,
            "inputSchema": input_schema,
            "outputSchema": output_schema,
            "entrypoint": entrypoint,
            "conversationId": "test",
        }
    )
    return _json(200, result)


def _handle_custom_tools_generate(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    _require_budget(claims)
    try:
        result = generate_tool(
            str(body.get("description") or ""),
            current_code=str(body.get("code") or ""),
            input_schema=body.get("inputSchema"),
            output_schema=body.get("outputSchema"),
            last_error=str(body.get("lastError") or ""),
        )
    except GenerationError as exc:
        raise ApiError(502, str(exc)) from exc
    return _json(200, result)


# --- Playground build sessions ------------------------------------------------
#
# The Playground chats with the code generator while building one custom MCP
# server/tool. One small DynamoDB item per session holds only the metadata the
# history list needs; the message transcript (including every generated
# proposal) is one S3 object, read-modify-written once per turn.


def _playground_title(raw: Any) -> str:
    return str(raw or "").strip()[:80]


def _serialize_playground_session(
    item: dict[str, Any], *, messages: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": item.get("sessionId"),
        "title": item.get("title") or "",
        "serverId": item.get("serverId"),
        "serverSlug": item.get("serverSlug"),
        "toolId": item.get("toolId"),
        "toolName": item.get("toolName"),
        "lastPreview": item.get("lastPreview") or "",
        "messageCount": int(item.get("messageCount") or 0),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }
    if messages is not None:
        payload["messages"] = messages
    return payload


def _playground_transcript(sub: str, session_id: str) -> list[dict[str, Any]]:
    """Load a session's message list from S3 (empty when the object is absent)."""
    try:
        data = _storage().get_json(layout.playground_key(sub, session_id))
    except Exception:  # noqa: BLE001 - a missing transcript is an empty chat
        return []
    messages = data.get("messages") if isinstance(data, dict) else None
    return messages if isinstance(messages, list) else []


def _save_playground_transcript(
    sub: str, session_id: str, messages: list[dict[str, Any]]
) -> None:
    _storage().put_json(
        layout.playground_key(sub, session_id),
        {
            "sessionId": session_id,
            "userId": sub,
            "messages": messages,
            "updatedAt": now_iso(),
        },
    )


def _playground_binding(
    sub: str, body: dict[str, Any]
) -> tuple[str | None, str | None, str | None, str | None]:
    """Resolve/validate a session's optional server + tool binding."""
    server_id = str(body.get("serverId") or "").strip() or None
    tool_id = str(body.get("toolId") or "").strip() or None
    server_slug: str | None = None
    tool_name: str | None = None
    if server_id:
        server = custom_tools_repo.get_server(sub, server_id)
        if server is None:
            raise ApiError(404, "Custom tool server not found")
        server_slug = str(server.get("slug") or "")
    if tool_id:
        tool = custom_tools_repo.get_tool(sub, tool_id)
        if tool is None:
            raise ApiError(404, "Custom tool not found")
        tool_name = str(tool.get("name") or "")
        if not server_id:
            server_id = str(tool.get("serverId") or "") or None
            server = (
                custom_tools_repo.get_server(sub, server_id) if server_id else None
            )
            server_slug = str(server.get("slug") or "") if server else None
    return server_id, server_slug, tool_id, tool_name


def _handle_playground_sessions_list(
    claims: dict[str, Any], query: dict[str, str]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    tool_id = (query.get("toolId") or "").strip()
    server_id = (query.get("serverId") or "").strip()
    sessions, _ = playground_repo.list_sessions(sub, limit=100)
    serialized = [_serialize_playground_session(item) for item in sessions]
    # Filtering by binding is an in-memory pass over one bounded page (no Scan).
    if tool_id:
        serialized = [item for item in serialized if item["toolId"] == tool_id]
    if server_id:
        serialized = [item for item in serialized if item["serverId"] == server_id]
    return _json(200, {"sessions": serialized})


def _handle_playground_sessions_create(
    claims: dict[str, Any], body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    limit = playground_repo.MAX_PLAYGROUND_SESSIONS_PER_USER
    if playground_repo.count_sessions(sub) >= limit:
        raise ApiError(409, f"You can start at most {limit} Playground sessions")
    server_id, server_slug, tool_id, tool_name = _playground_binding(sub, body)
    session = playground_repo.create_session(
        user_id=sub,
        session_id=str(uuid.uuid4()),
        title=_playground_title(body.get("title")),
        server_id=server_id,
        server_slug=server_slug,
        tool_id=tool_id,
        tool_name=tool_name,
    )
    return _json(201, _serialize_playground_session(session, messages=[]))


def _get_playground_session_or_404(sub: str, session_id: str) -> dict[str, Any]:
    session = playground_repo.get_session(sub, session_id)
    if session is None:
        raise ApiError(404, "Playground session not found")
    return session


def _handle_playground_session_detail(
    claims: dict[str, Any], session_id: str
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    session = _get_playground_session_or_404(sub, session_id)
    return _json(
        200,
        _serialize_playground_session(
            session, messages=_playground_transcript(sub, session_id)
        ),
    )


def _handle_playground_session_update(
    claims: dict[str, Any], session_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    _get_playground_session_or_404(sub, session_id)
    title = body.get("title")
    server_id = server_slug = tool_id = tool_name = None
    if "serverId" in body or "toolId" in body:
        server_id, server_slug, tool_id, tool_name = _playground_binding(sub, body)
    playground_repo.touch_session(
        sub,
        session_id,
        title=_playground_title(title) if title is not None else None,
        server_id=server_id,
        server_slug=server_slug,
        tool_id=tool_id,
        tool_name=tool_name,
    )
    session = playground_repo.get_session(sub, session_id) or {}
    return _json(200, _serialize_playground_session(session))


def _handle_playground_session_delete(
    claims: dict[str, Any], session_id: str
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    _get_playground_session_or_404(sub, session_id)
    playground_repo.delete_session(sub, session_id)
    try:
        _storage().delete(layout.playground_key(sub, session_id))
    except Exception:  # noqa: BLE001 - best effort cleanup
        pass
    return _json(200, {"ok": True})


def _finish_playground_turn(
    sub: str,
    session: dict[str, Any],
    session_id: str,
    messages: list[dict[str, Any]],
    prompt: str,
) -> None:
    """Trim + persist the transcript, then refresh the session metadata item."""
    trimmed = messages[-playground_repo.MAX_PLAYGROUND_MESSAGES :]
    _save_playground_transcript(sub, session_id, trimmed)
    title = prompt[:80] if not str(session.get("title") or "").strip() else None
    playground_repo.touch_session(
        sub,
        session_id,
        title=title,
        preview=prompt,
        message_count=len(trimmed),
    )


def _playground_assistant_message(
    message_id: str,
    status: str,
    text: str,
    *,
    code: str | None = None,
    generated: dict[str, Any] | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "id": message_id,
        "role": "assistant",
        "status": status,
        "text": text,
        "createdAt": now_iso(),
    }
    if generated is not None:
        message["generated"] = generated
        # The code the proposal was generated from, so the client can show the
        # exact diff for this step later (the proposal itself is `generated`).
        message["baseCode"] = code or ""
    return message


def _replace_playground_message(
    messages: list[dict[str, Any]], message_id: str, replacement: dict[str, Any]
) -> list[dict[str, Any]]:
    replaced = False
    out: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, dict) and message.get("id") == message_id:
            out.append(replacement)
            replaced = True
        else:
            out.append(message)
    if not replaced:
        out.append(replacement)
    return out


def _run_playground_generate_job(job: dict[str, Any]) -> dict[str, Any]:
    """Background worker: run generation and resolve the placeholder message."""
    sub = str(job.get("userId") or "")
    session_id = str(job.get("sessionId") or "")
    assistant_id = str(job.get("assistantId") or "")
    prompt = str(job.get("prompt") or "")
    code = str(job.get("code") or "")
    session = playground_repo.get_session(sub, session_id)
    if session is None:
        return {"ok": False, "error": "Playground session not found"}

    try:
        generated = generate_tool(
            prompt,
            current_code=code,
            input_schema=job.get("inputSchema"),
            output_schema=job.get("outputSchema"),
            last_error=str(job.get("lastError") or ""),
            timeout_seconds=async_timeout(),
        )
    except GenerationError as exc:
        replacement = _playground_assistant_message(assistant_id, "error", str(exc))
    except Exception as exc:  # noqa: BLE001 - never leave a stuck placeholder
        print(f"playground generation failed: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        replacement = _playground_assistant_message(
            assistant_id, "error", "Code generation failed. Try again."
        )
    else:
        replacement = _playground_assistant_message(
            assistant_id,
            "ok",
            generated.get("description") or f"Updated {generated.get('name')}",
            code=code,
            generated=generated,
        )

    messages = _playground_transcript(sub, session_id)
    messages = _replace_playground_message(messages, assistant_id, replacement)
    _finish_playground_turn(sub, session, session_id, messages, prompt)
    return {"ok": True}


def _handle_playground_session_turn(
    claims: dict[str, Any], session_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    session = _get_playground_session_or_404(sub, session_id)

    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        raise ApiError(400, "Describe what to build or change")
    if len(prompt) > playground_repo.MAX_PLAYGROUND_PROMPT_CHARS:
        raise ApiError(400, "Description is too long")
    code = str(body.get("code") or "")
    last_error = str(body.get("lastError") or "")[:2000]

    messages = _playground_transcript(sub, session_id)
    user_message = {
        "id": str(uuid.uuid4()),
        "role": "user",
        "text": prompt,
        "createdAt": now_iso(),
    }
    assistant_id = str(uuid.uuid4())
    placeholder = _playground_assistant_message(assistant_id, "generating", "")
    messages.append(user_message)
    messages.append(placeholder)
    # Persist the pending turn first so a poll sees it immediately, then start
    # generation in the background (past the API Gateway 30s integration cap).
    _finish_playground_turn(sub, session, session_id, messages, prompt)
    try:
        _invoke_self_async(
            {
                _ASYNC_ACTION: "playground.generate",
                "userId": sub,
                "sessionId": session_id,
                "assistantId": assistant_id,
                "prompt": prompt,
                "code": code,
                "inputSchema": body.get("inputSchema"),
                "outputSchema": body.get("outputSchema"),
                "lastError": last_error,
            }
        )
    except ApiError:
        replacement = _playground_assistant_message(
            assistant_id, "error", "Could not start code generation. Try again."
        )
        messages = _replace_playground_message(messages, assistant_id, replacement)
        _finish_playground_turn(sub, session, session_id, messages, prompt)
        return _json(200, {"messages": [user_message, replacement]})

    return _json(200, {"messages": [user_message, placeholder]})


def _route_playground_sessions(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
    query: dict[str, str],
):
    if not rest:
        if method == "GET":
            return _handle_playground_sessions_list(claims, query)
        if method == "POST":
            return _handle_playground_sessions_create(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    session_id = _parse_id(rest[0], "Playground session")

    if len(rest) == 1:
        if method == "GET":
            return _handle_playground_session_detail(claims, session_id)
        if method == "PATCH":
            return _handle_playground_session_update(claims, session_id, body)
        if method == "DELETE":
            return _handle_playground_session_delete(claims, session_id)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 2 and rest[1] == "turn":
        if method == "POST":
            return _handle_playground_session_turn(claims, session_id, body)
        raise ApiError(405, f"Method not allowed: {method}")

    raise ApiError(404, "Not found")


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
        "providerSecretId": config.get("providerSecretId") or "",
        "reasoning": config.get("reasoning") or "low",
        "answerMode": config.get("answerMode") or "summarize",
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


def _validated_optional_id(value: Any, label: str) -> str:
    """An optional single id (empty string means "not set")."""
    if value is None or str(value).strip() == "":
        return ""
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ApiError(400, f"{label} must be a valid id") from exc


def _validated_free_model(value: Any) -> str:
    """A model id for a user's Vault provider — free-form but bounded."""
    model = str(value or "").strip()
    if not model:
        return ""
    if len(model) > 120:
        raise ApiError(400, "model must be at most 120 characters")
    if not re.fullmatch(r"[A-Za-z0-9._:/-]+", model):
        raise ApiError(400, "model contains unsupported characters")
    return model


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
        if source not in ("builtin", "mcp", "custom"):
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


def _validated_guardrail(value: Any) -> dict[str, Any]:
    """The Bedrock guardrail a run applies: ``{enabled, id}``.

    The version is never user-chosen — it defaults to ``DRAFT`` (Bedrock's
    working version) — so only the id is stored. An empty id means "inherit the
    workspace default"; ``enabled=False`` opts the agent/workflow out entirely.
    """
    if not isinstance(value, dict):
        return {"enabled": True, "id": ""}
    guardrail_id = str(value.get("id") or "").strip()
    if guardrail_id and not re.match(r"^[A-Za-z0-9_-]{1,64}$", guardrail_id):
        raise ApiError(400, "guardrail.id must be alphanumeric (with - or _)")
    return {
        "enabled": _validated_toggle("guardrail.enabled", value.get("enabled", True)),
        "id": guardrail_id,
    }


def _validated_guardrail_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "Guardrail name is required")
    name = value.strip().lower()
    if len(name) < GUARDRAIL_NAME_MIN or len(name) > GUARDRAIL_NAME_MAX:
        raise ApiError(400, f"Name must be at most {GUARDRAIL_NAME_MAX} characters")
    if not _AGENT_NAME_CHARS.match(name):
        raise ApiError(
            400,
            "Name can only contain lowercase letters, numbers and hyphens "
            "(no spaces or special characters)",
        )
    if not _AGENT_NAME_EDGES.match(name):
        raise ApiError(400, "Name must start and end with a letter or number")
    if name in _GUARDRAIL_RESERVED:
        raise ApiError(400, f'"{name}" is a reserved guardrail name')
    return name


def _bounded_text(value: Any, label: str, limit: int, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ApiError(400, f"{label} is required")
    if len(text) > limit:
        raise ApiError(400, f"{label} must be at most {limit} characters")
    return text


def _validated_guardrail_config(value: Any) -> dict[str, Any]:
    """Normalize the guardrail policy the editor sends, with bounds + enums."""
    from core import guardrails as core_guardrails

    data = value if isinstance(value, dict) else {}

    raw_filters = data.get("contentFilters")
    filters: list[dict[str, str]] = []
    for raw in raw_filters if isinstance(raw_filters, list) else []:
        item = raw if isinstance(raw, dict) else {}
        filter_type = str(item.get("type") or "").strip().upper()
        if filter_type not in core_guardrails.CONTENT_FILTER_TYPES:
            raise ApiError(400, f"Unknown content filter type: {filter_type or '(empty)'}")
        input_strength = str(item.get("inputStrength") or "HIGH").strip().upper()
        output_strength = str(item.get("outputStrength") or "HIGH").strip().upper()
        if input_strength not in core_guardrails.STRENGTHS:
            raise ApiError(400, f"Invalid content filter strength: {input_strength}")
        if filter_type == "PROMPT_ATTACK":
            output_strength = "NONE"
        elif output_strength not in core_guardrails.STRENGTHS:
            raise ApiError(400, f"Invalid content filter strength: {output_strength}")
        filters.append(
            {
                "type": filter_type,
                "inputStrength": input_strength,
                "outputStrength": output_strength,
            }
        )

    raw_topics = data.get("deniedTopics")
    topics: list[dict[str, Any]] = []
    for raw in raw_topics if isinstance(raw_topics, list) else []:
        item = raw if isinstance(raw, dict) else {}
        name = _bounded_text(
            item.get("name"), "Denied topic name", MAX_GUARDRAIL_TOPIC_NAME, required=True
        )
        definition = _bounded_text(
            item.get("definition"),
            "Denied topic definition",
            MAX_GUARDRAIL_TOPIC_DEFINITION,
            required=True,
        )
        examples: list[str] = []
        raw_examples = item.get("examples")
        for example in raw_examples if isinstance(raw_examples, list) else []:
            text = _bounded_text(example, "Denied topic example", 100)
            if text:
                examples.append(text)
        topics.append({"name": name, "definition": definition, "examples": examples[:5]})
    if len(topics) > MAX_GUARDRAIL_TOPICS:
        raise ApiError(400, f"At most {MAX_GUARDRAIL_TOPICS} denied topics are allowed")

    raw_words = data.get("wordFilters")
    word_filters = raw_words if isinstance(raw_words, dict) else {}
    words: list[str] = []
    raw_word_list = word_filters.get("words")
    for raw in raw_word_list if isinstance(raw_word_list, list) else []:
        text = _bounded_text(raw, "Word filter", 100)
        if text:
            words.append(text)
    if len(words) > MAX_GUARDRAIL_WORDS:
        raise ApiError(400, f"At most {MAX_GUARDRAIL_WORDS} words are allowed")
    profanity = bool(word_filters.get("profanity"))

    raw_sensitive = data.get("sensitiveInfo")
    sensitive = raw_sensitive if isinstance(raw_sensitive, dict) else {}
    pii: list[dict[str, str]] = []
    raw_pii = sensitive.get("pii")
    for raw in raw_pii if isinstance(raw_pii, list) else []:
        item = raw if isinstance(raw, dict) else {}
        entity_type = str(item.get("type") or "").strip().upper()
        if not entity_type:
            continue
        action = str(item.get("action") or "ANONYMIZE").strip().upper()
        if action not in core_guardrails.PII_ACTIONS:
            raise ApiError(400, f"Invalid PII action: {action}")
        pii.append({"type": entity_type, "action": action})
    regexes: list[dict[str, str]] = []
    raw_regexes = sensitive.get("regexes")
    for raw in raw_regexes if isinstance(raw_regexes, list) else []:
        item = raw if isinstance(raw, dict) else {}
        name = _bounded_text(item.get("name"), "Regex name", 100, required=True)
        pattern = _bounded_text(item.get("pattern"), "Regex pattern", 500, required=True)
        action = str(item.get("action") or "BLOCK").strip().upper()
        if action not in core_guardrails.PII_ACTIONS:
            raise ApiError(400, f"Invalid regex action: {action}")
        regexes.append({"name": name, "pattern": pattern, "action": action})
    if len(regexes) > MAX_GUARDRAIL_REGEXES:
        raise ApiError(400, f"At most {MAX_GUARDRAIL_REGEXES} regex patterns are allowed")

    raw_grounding = data.get("contextualGrounding")
    grounding: list[dict[str, Any]] = []
    for raw in raw_grounding if isinstance(raw_grounding, list) else []:
        item = raw if isinstance(raw, dict) else {}
        grounding_type = str(item.get("type") or "").strip().upper()
        if grounding_type not in core_guardrails.GROUNDING_TYPES:
            raise ApiError(400, f"Invalid contextual grounding type: {grounding_type or '(empty)'}")
        try:
            threshold = float(item.get("threshold"))
        except (TypeError, ValueError):
            threshold = 0.7
        action = str(item.get("action") or "BLOCK").strip().upper()
        if action not in core_guardrails.GROUNDING_ACTIONS:
            raise ApiError(400, f"Invalid contextual grounding action: {action}")
        grounding.append(
            {
                "type": grounding_type,
                "threshold": max(0.0, min(0.99, threshold)),
                "action": action,
            }
        )

    normalized = {
        "contentFilters": filters,
        "deniedTopics": topics,
        "wordFilters": {"profanity": profanity, "words": words},
        "sensitiveInfo": {"pii": pii, "regexes": regexes},
        "contextualGrounding": grounding,
    }
    if not any((filters, topics, words, profanity, pii, regexes, grounding)):
        # A brand-new guardrail with no policy is useless; start from the
        # standard harmful-content set instead of an inert guardrail.
        return core_guardrails.default_policy_config()
    return normalized


def _serialize_guardrail(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("name") or ""),
        "name": str(item.get("name") or ""),
        "description": str(item.get("description") or ""),
        "guardrailId": str(item.get("guardrailId") or ""),
        "guardrailArn": str(item.get("guardrailArn") or ""),
        "version": str(item.get("version") or "DRAFT"),
        "status": str(item.get("status") or "READY"),
        "config": item.get("config") or {},
        "blockedInput": str(item.get("blockedInput") or ""),
        "blockedOutput": str(item.get("blockedOutput") or ""),
        "createdAt": str(item.get("createdAt") or ""),
        "updatedAt": str(item.get("updatedAt") or ""),
    }



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

    # When the agent runs on one of the user's Vault provider secrets, its model
    # is whatever that provider serves (free-form); otherwise it must be a
    # model the platform gateway exposes.
    provider_secret_id = _validated_optional_id(
        value.get("providerSecretId"), "providerSecretId"
    )
    if provider_secret_id:
        model = _validated_free_model(value.get("model"))
    else:
        model = _validated_model(
            value.get("model"), SUPPORTED_AGENT_MODELS, "model", SUPPORTED_AGENT_MODELS[0]
        )

    config: dict[str, Any] = {
        "version": version,
        "prompt": prompt,
        "model": model,
        "providerSecretId": provider_secret_id,
        "reasoning": _validated_enum(
            value.get("reasoning"), AGENT_REASONING_LEVELS, "reasoning", "low"
        ),
        "answerMode": _validated_enum(
            value.get("answerMode"), AGENT_ANSWER_MODES, "answerMode", "summarize"
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
        "guardrail": _validated_guardrail(value.get("guardrail")),
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

    provider_secret_id = str(config.get("providerSecretId") or "").strip()
    if provider_secret_id:
        provider = vault_repo.get_secret(sub, provider_secret_id)
        if provider is None:
            errors.append("The selected model provider no longer exists.")
        elif provider.get("kind") != "provider":
            errors.append("The selected model provider is not a provider secret.")
        elif not provider.get("baseUrl"):
            errors.append("The selected model provider has no base URL.")

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


def _sync_schedule(
    user_id: str, kind: str, target_id: str, name: str, config: dict[str, Any]
) -> None:
    """Mirror an agent/workflow schedule into the scheduler registry.

    Best-effort: a scheduling write must never break saving the entity.
    """
    schedule = config.get("schedule") or {}
    input_config = config.get("input") or {}
    try:
        schedules_repo.upsert_schedule(
            user_id,
            kind,
            target_id,
            name=name,
            expression=str(schedule.get("cron") or ""),
            timezone=str(schedule.get("timezone") or "UTC"),
            enabled=bool(schedule.get("enabled")),
            payload={"query": str(input_config.get("query") or "")},
        )
    except Exception:  # noqa: BLE001 - scheduling must never break a save
        pass


def _clear_schedule(user_id: str, kind: str, target_id: str) -> None:
    try:
        schedules_repo.delete_schedule(user_id, kind, target_id)
    except Exception:  # noqa: BLE001
        pass


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
    _sync_schedule(sub, "agent", str(agent["agentId"]), str(agent.get("name") or name), agent.get("config") or {})
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
    _sync_schedule(sub, "agent", agent_id, str(agent.get("name") or name), agent.get("config") or {})
    return _json(200, _serialize_agent(agent, include_config=True))


def _handle_agent_delete(claims: dict[str, Any], agent_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    _get_agent_or_404(sub, agent_id)
    agents_repo.delete_agent(sub, agent_id)
    _clear_schedule(sub, "agent", agent_id)
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


# --- vault (encrypted secrets) ------------------------------------------------
#
# One item per secret (USER#<userId> / VAULT#<name>). The secret material is
# KMS-encrypted (core.crypto, VAULT_KMS_KEY_ARN) and bound to {userId,
# secretId}; the API never returns it, only a masked preview. Secrets can be
# referenced as {{vault:name}} wherever a stored value is resolved from the
# vault (e.g. an MCP server API key).


def _validate_vault_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    if not name:
        raise ApiError(400, "A name is required")
    if len(name) > MAX_VAULT_NAME_LENGTH:
        raise ApiError(400, f"Name must be at most {MAX_VAULT_NAME_LENGTH} characters")
    if not _VAULT_NAME_CHARS.match(name):
        raise ApiError(
            400, "Name can only contain lowercase letters, numbers and hyphens"
        )
    if not _VAULT_NAME_EDGES.match(name):
        raise ApiError(400, "Name must start and end with a letter or number")
    return name


def _clean_vault_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _clean_vault_base_url(value: Any) -> str:
    url = str(value or "").strip().rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ApiError(400, "Base URL must be a valid http(s) URL")
    return url[:MAX_VAULT_BASE_URL_LENGTH]


def _vault_primary_field(kind: str) -> str:
    return "apiKey" if kind == "provider" else "value"


def _collect_vault_fields(
    body: dict[str, Any], kind: str, existing: dict[str, str] | None = None
) -> dict[str, str]:
    """Merge a request body's secret fields over the stored ones (update case)."""
    fields = dict(existing or {})
    provided: str | None = None
    for key in ("secret", "apiKey", "value", "token", "password"):
        candidate = body.get(key)
        if isinstance(candidate, str) and candidate.strip():
            provided = candidate.strip()
            break
    if provided is not None:
        fields[_vault_primary_field(kind)] = provided

    extra = body.get("extraFields")
    if isinstance(extra, dict):
        for raw_key, raw_value in extra.items():
            try:
                field = vault_repo.validate_field_name(str(raw_key).strip().lower())
            except ValueError as exc:
                raise ApiError(400, str(exc)) from exc
            if raw_value is None or str(raw_value) == "":
                fields.pop(field, None)
            else:
                fields[field] = str(raw_value)

    if not fields.get(_vault_primary_field(kind)):
        raise ApiError(400, "A secret value is required")
    encoded = len(
        json.dumps({"fields": fields}, separators=(",", ":")).encode("utf-8")
    )
    if encoded > VAULT_PAYLOAD_LIMIT_BYTES:
        raise ApiError(
            413,
            f"Secret is too large ({encoded} bytes). Keep the stored value under "
            f"{VAULT_PAYLOAD_LIMIT_BYTES} bytes.",
        )
    return fields


def _serialize_vault_secret(item: dict[str, Any]) -> dict[str, Any]:
    """Public shape — deliberately excludes ``payloadEnc`` and every plaintext."""
    return {
        "id": item.get("secretId"),
        "name": item.get("name"),
        "label": item.get("label") or item.get("name"),
        "description": item.get("description") or "",
        "kind": item.get("kind") or "generic",
        "provider": item.get("provider") or "",
        "baseUrl": item.get("baseUrl") or "",
        "defaultModel": item.get("defaultModel") or "",
        "models": item.get("models") or [],
        "fields": item.get("fields") or [],
        "preview": item.get("preview") or "",
        "usage": {
            "count": int(item.get("usageCount") or 0),
            "lastUsedAt": item.get("lastUsedAt"),
            "runs": int(item.get("runCount") or 0),
            "tokensIn": int(item.get("tokensIn") or 0),
            "tokensOut": int(item.get("tokensOut") or 0),
            "tokensTotal": int(item.get("tokensTotal") or 0),
            "lastModel": item.get("lastModel") or "",
        },
        "test": {
            "status": item.get("lastTestStatus") or "",
            "message": item.get("lastTestMessage") or "",
            "latencyMs": item.get("lastTestLatencyMs"),
            "models": item.get("lastTestModels") or [],
            "at": item.get("lastTestedAt"),
        },
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }


def _clean_vault_models(value: Any) -> list[str]:
    """Normalize a provider's model list (deduped, ordered, bounded)."""
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ApiError(400, "models must be a list")
    models: list[str] = []
    for raw in value:
        model = _validated_free_model(raw)
        if model and model not in models:
            models.append(model)
    if len(models) > MAX_VAULT_MODELS:
        raise ApiError(400, f"At most {MAX_VAULT_MODELS} models are allowed")
    return models


def _vault_provider_config(
    kind: str, body: dict[str, Any], existing: dict[str, Any] | None = None
) -> tuple[str, str, str, list[str]]:
    """Resolve ``(provider, baseUrl, defaultModel, models)`` for a create/update."""
    if kind != "provider":
        return "", "", "", []
    preset = get_vault_provider(body.get("provider")) or get_vault_provider("custom")
    provider_id = preset["id"]

    base_url = _clean_vault_text(body.get("baseUrl"), MAX_VAULT_BASE_URL_LENGTH)
    if not base_url and existing is not None:
        base_url = str(existing.get("baseUrl") or "")
    if not base_url:
        base_url = str(preset.get("baseUrl") or "")
    if not base_url:
        raise ApiError(400, "A base URL is required for a provider secret")
    base_url = _clean_vault_base_url(base_url)

    # A provider may offer several models; the default is the first one.
    raw_models = body.get("models")
    if raw_models is None and existing is not None:
        models = [str(entry) for entry in (existing.get("models") or []) if str(entry)]
    else:
        models = _clean_vault_models(raw_models)

    model = _clean_vault_text(body.get("defaultModel"), MAX_VAULT_MODEL_LENGTH)
    if not model and existing is not None:
        model = str(existing.get("defaultModel") or "")
    if not model:
        model = models[0] if models else str(preset.get("defaultModel") or "")
    if model and model not in models:
        models = [model, *models]
    return provider_id, base_url, model, models[:MAX_VAULT_MODELS]


def _handle_vault_providers(claims: dict[str, Any]) -> dict[str, Any]:
    get_or_create_user(claims)
    return _json(200, {"providers": vault_provider_list()})


def _handle_vault_list(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    items = vault_repo.list_secrets(sub)
    uses = sum(int(item.get("usageCount") or 0) for item in items)
    last_used = max((str(item.get("lastUsedAt") or "") for item in items), default="")
    last_tested = max((str(item.get("lastTestedAt") or "") for item in items), default="")
    return _json(
        200,
        {
            "secrets": [_serialize_vault_secret(item) for item in items],
            "usage": {
                "secretCount": len(items),
                "limit": MAX_VAULT_SECRETS,
                "providerCount": sum(
                    1 for item in items if item.get("kind") == "provider"
                ),
                "uses": uses,
                "lastUsedAt": last_used or None,
                "lastTestedAt": last_tested or None,
            },
        },
    )


def _handle_vault_get(claims: dict[str, Any], secret_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    secret_id = _parse_id(secret_id, "Secret")
    item = vault_repo.get_secret(sub, secret_id)
    if item is None:
        raise ApiError(404, "Secret not found")
    return _json(200, _serialize_vault_secret(item))


def _handle_vault_create(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    if vault_repo.count_secrets(sub) >= MAX_VAULT_SECRETS:
        raise ApiError(409, f"You can store at most {MAX_VAULT_SECRETS} secrets")

    name = _validate_vault_name(body.get("name"))
    kind = "provider" if str(body.get("kind") or "").strip() == "provider" else "generic"
    provider_id, base_url, model, models = _vault_provider_config(kind, body)
    fields = _collect_vault_fields(body, kind)
    secret_id = str(uuid.uuid4())
    primary = vault_repo.primary_value(fields) or ""
    item = vault_repo.vault_item(
        secret_id=secret_id,
        user_id=sub,
        name=name,
        # The reference name is the display label; there is no separate field.
        label=name,
        description=_clean_vault_text(body.get("description"), MAX_VAULT_DESCRIPTION_LENGTH),
        kind=kind,
        provider=provider_id,
        base_url=base_url,
        default_model=model,
        payload_enc=vault_repo.seal_payload(sub, secret_id, fields),
        fields=sorted(fields),
        preview=vault_repo.mask_preview(primary),
        models=models,
    )
    try:
        vault_repo.create_secret(item)
    except DuplicateVaultSecret as exc:
        raise ApiError(409, "A secret with this name already exists") from exc
    return _json(201, _serialize_vault_secret(item))


def _handle_vault_update(
    claims: dict[str, Any], secret_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    secret_id = _parse_id(secret_id, "Secret")
    existing = vault_repo.get_secret(sub, secret_id)
    if existing is None:
        raise ApiError(404, "Secret not found")

    name = _validate_vault_name(body.get("name") or existing.get("name"))
    requested_kind = str(body.get("kind") or "").strip()
    kind = (
        requested_kind
        if requested_kind in ("provider", "generic")
        else str(existing.get("kind") or "generic")
    )
    provider_id, base_url, model, models = _vault_provider_config(kind, body, existing)
    existing_fields = vault_repo.open_payload(sub, existing)
    fields = _collect_vault_fields(body, kind, existing=existing_fields)
    primary = vault_repo.primary_value(fields) or ""

    updated = vault_repo.vault_item(
        secret_id=secret_id,
        user_id=sub,
        name=name,
        label=name,
        description=(
            _clean_vault_text(body.get("description"), MAX_VAULT_DESCRIPTION_LENGTH)
            if body.get("description") is not None
            else str(existing.get("description") or "")
        ),
        kind=kind,
        provider=provider_id,
        base_url=base_url,
        default_model=model,
        payload_enc=vault_repo.seal_payload(sub, secret_id, fields),
        fields=sorted(fields),
        preview=vault_repo.mask_preview(primary),
        models=models,
    )
    try:
        vault_repo.update_secret(sub, updated)
    except DuplicateVaultSecret as exc:
        raise ApiError(409, "A secret with this name already exists") from exc
    return _json(200, _serialize_vault_secret(updated))


def _handle_vault_delete(claims: dict[str, Any], secret_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    secret_id = _parse_id(secret_id, "Secret")
    if vault_repo.delete_secret(sub, secret_id) is None:
        raise ApiError(404, "Secret not found")
    return _json(200, {"ok": True})


def _handle_vault_reveal(claims: dict[str, Any], secret_id: str) -> dict[str, Any]:
    """Decrypt one secret for its owner. Plaintext is never logged."""
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    secret_id = _parse_id(secret_id, "Secret")
    item = vault_repo.get_secret(sub, secret_id)
    if item is None:
        raise ApiError(404, "Secret not found")
    return _json(
        200,
        {
            "id": item.get("secretId"),
            "name": item.get("name"),
            "fields": vault_repo.open_payload(sub, item),
        },
    )


def _run_vault_test(
    *, provider: str, base_url: str, api_key: str, model: str
) -> dict[str, Any]:
    try:
        return test_vault_provider(
            provider_id=provider,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
    except VaultTestError as exc:
        return {
            "ok": False,
            "provider": provider or "custom",
            "baseUrl": base_url,
            "status": None,
            "latencyMs": None,
            "models": [],
            "model": model or None,
            "sample": None,
            "usage": None,
            "message": str(exc),
            "checkedAt": now_iso(),
        }


def _handle_vault_test(
    claims: dict[str, Any], secret_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    secret_id = _parse_id(secret_id, "Secret")
    item = vault_repo.get_secret(sub, secret_id)
    if item is None:
        raise ApiError(404, "Secret not found")

    api_key = vault_repo.primary_value(vault_repo.open_payload(sub, item)) or ""
    model = _clean_vault_text(body.get("model"), MAX_VAULT_MODEL_LENGTH) or str(
        item.get("defaultModel") or ""
    )
    result = _run_vault_test(
        provider=str(item.get("provider") or "custom"),
        base_url=str(item.get("baseUrl") or ""),
        api_key=api_key,
        model=model,
    )
    vault_repo.record_test(
        sub,
        secret_id,
        ok=bool(result.get("ok")),
        message=str(result.get("message") or ""),
        latency_ms=result.get("latencyMs"),
        models=result.get("models"),
    )
    return _json(200, result)


def _handle_vault_models(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Fetch the models a provider serves (server-side; the key never leaves)."""
    get_or_create_user(claims)
    provider = str(body.get("provider") or "custom").strip() or "custom"
    base_url = _clean_vault_text(body.get("baseUrl"), MAX_VAULT_BASE_URL_LENGTH)
    api_key = ""
    for key in ("secret", "apiKey", "value", "token", "password"):
        candidate = body.get(key)
        if isinstance(candidate, str) and candidate.strip():
            api_key = candidate.strip()
            break
    if not base_url:
        raise ApiError(400, "A base URL is required to fetch models")
    try:
        return _json(
            200,
            list_vault_models(
                provider_id=provider, base_url=base_url, api_key=api_key
            ),
        )
    except VaultTestError as exc:
        return _json(
            200,
            {"ok": False, "status": None, "latencyMs": None, "models": [], "message": str(exc)},
        )


def _handle_vault_test_adhoc(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Test an unsaved key straight from the create dialog."""
    get_or_create_user(claims)
    provider = str(body.get("provider") or "custom").strip() or "custom"
    base_url = _clean_vault_text(body.get("baseUrl"), MAX_VAULT_BASE_URL_LENGTH)
    model = _clean_vault_text(body.get("model"), MAX_VAULT_MODEL_LENGTH)
    api_key = ""
    for key in ("secret", "apiKey", "value", "token", "password"):
        candidate = body.get(key)
        if isinstance(candidate, str) and candidate.strip():
            api_key = candidate.strip()
            break
    if not base_url:
        raise ApiError(400, "A base URL is required to test a provider")
    return _json(
        200,
        _run_vault_test(
            provider=provider, base_url=base_url, api_key=api_key, model=model
        ),
    )


def _route_vault(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
):
    if rest == ["providers"]:
        if method == "GET":
            return _handle_vault_providers(claims)
        raise ApiError(405, f"Method not allowed: {method}")

    if rest == ["test"]:
        if method == "POST":
            return _handle_vault_test_adhoc(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    if rest == ["models"]:
        if method == "POST":
            return _handle_vault_models(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    if rest == ["secrets"]:
        if method == "GET":
            return _handle_vault_list(claims)
        if method == "POST":
            return _handle_vault_create(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    if rest and rest[0] == "secrets":
        if len(rest) == 2:
            if method == "GET":
                return _handle_vault_get(claims, rest[1])
            if method == "PUT":
                return _handle_vault_update(claims, rest[1], body)
            if method == "DELETE":
                return _handle_vault_delete(claims, rest[1])
            raise ApiError(405, f"Method not allowed: {method}")
        if len(rest) == 3 and rest[2] == "test":
            if method == "POST":
                return _handle_vault_test(claims, rest[1], body)
            raise ApiError(405, f"Method not allowed: {method}")
        if len(rest) == 3 and rest[2] == "reveal":
            if method == "POST":
                return _handle_vault_reveal(claims, rest[1])
            raise ApiError(405, f"Method not allowed: {method}")

    raise ApiError(404, "Not found")


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
    payload = _serialize_account(profile, settings, prefs)
    # LLM budget + per-model rates, so the UI can show remaining dollars.
    budget = get_budget(sub)
    payload["budget"] = {
        "budgetUsd": core_usage.usd(budget.budget_micro_usd),
        "spentUsd": core_usage.usd(budget.spent_micro_usd),
        "remainingUsd": None
        if budget.unlimited
        else core_usage.usd(budget.remaining_micro_usd),
        "unlimited": budget.unlimited,
        # The same amounts expressed as AI credits (the UI's unit).
        "creditsPerUsd": core_usage.CREDITS_PER_USD,
        "budgetCredits": round(core_usage.usd_to_credits(budget.budget_micro_usd), 2),
        "spentCredits": round(core_usage.usd_to_credits(budget.spent_micro_usd), 2),
        "remainingCredits": None
        if budget.unlimited
        else round(core_usage.usd_to_credits(budget.remaining_micro_usd), 2),
    }
    payload["pricing"] = core_usage.pricing_table()
    return _json(200, payload)


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


# --- privacy & data rights (DPDP Act, 2023) ----------------------------------
#
# Implements the Data Principal rights the platform must offer: access (export),
# correction (profile/resource edits), erasure (account closure), grievance
# redressal, and a recorded, withdrawable consent. Nothing here is cached and
# nothing is best-effort when it concerns the user's own data — except S3 cleanup
# and Auth0 removal, which are logged and reported rather than allowed to block
# the erasure.

# Published contact for grievances (DPDP Rules require this to be readily
# available). Env-overridable so the address stays a config, not a code change.
GRIEVANCE_OFFICER_NAME = os.environ.get(
    "PRIVACY_OFFICER_NAME", "Data Protection & Grievance Officer, get1agent"
)
GRIEVANCE_OFFICER_EMAIL = os.environ.get(
    "PRIVACY_OFFICER_EMAIL", "techwithkiranavinash@gmail.com"
)
GRIEVANCE_RESPONSE_DAYS = int(os.environ.get("PRIVACY_RESPONSE_DAYS", "90"))
DPB_NAME = "Data Protection Board of India"
DPB_URL = "https://www.meity.gov.in/data-protection-framework"

REQUEST_TYPES = (
    "access",
    "correction",
    "erasure",
    "consent",
    "grievance",
    "other",
)

# Sensitive attribute suffixes that must never leave the API (encrypted payloads,
# tokens, secrets). Applied to every exported item.
_SENSITIVE_SUFFIXES = ("enc", "token", "secret", "password", "credential")


def _public_item(item: dict[str, Any]) -> dict[str, Any]:
    """A user's own item, stripped of internal keys and secret material."""
    public: dict[str, Any] = {}
    for key, value in item.items():
        lowered = str(key).lower()
        if key in {"pk", "sk", "entity"} or lowered.startswith("gsi"):
            continue
        if lowered.endswith(_SENSITIVE_SUFFIXES):
            continue
        public[key] = value
    return public


def _privacy_contact() -> dict[str, Any]:
    return {
        "officer": GRIEVANCE_OFFICER_NAME,
        "email": GRIEVANCE_OFFICER_EMAIL,
        "responseDays": GRIEVANCE_RESPONSE_DAYS,
        "board": DPB_NAME,
        "boardUrl": DPB_URL,
        "noticeVersion": consent_repo.CONSENT_VERSION,
    }


def _handle_consent_get(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    return _json(
        200,
        {
            "version": consent_repo.CONSENT_VERSION,
            "purposes": consent_repo.PURPOSES,
            "consent": consent_repo.get_consent(profile["userId"]),
            "contact": _privacy_contact(),
        },
    )


def _handle_consent_post(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    if body.get("adultConfirmed") is not True:
        raise ApiError(400, "You must confirm you are 18 or older to use get1agent")
    allowed = {purpose["id"] for purpose in consent_repo.PURPOSES}
    required = {
        purpose["id"] for purpose in consent_repo.PURPOSES if purpose.get("required")
    }
    raw = body.get("purposes")
    purposes = [str(item) for item in raw] if isinstance(raw, list) else []
    purposes = [item for item in purposes if item in allowed]
    missing = required - set(purposes)
    if missing:
        raise ApiError(
            400, "All required purposes must be accepted: " + ", ".join(sorted(missing))
        )
    language = str(body.get("language") or "en")[:16]
    record = consent_repo.record_consent(
        profile["userId"],
        purposes=purposes,
        adult_confirmed=True,
        language=language,
    )
    return _json(200, {"consent": record, "contact": _privacy_contact()})


def _handle_consent_withdraw(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    record = consent_repo.withdraw_consent(profile["userId"])
    if record is None:
        raise ApiError(404, "No consent record found")
    # Core processing cannot continue without consent; the account must be
    # closed. The UI routes the user to account deletion from here.
    return _json(
        200,
        {
            "consent": record,
            "action": "delete_account",
            "message": (
                "Consent withdrawn. Because processing is necessary to provide the "
                "service, your account and its data will be erased when you confirm "
                "account deletion."
            ),
            "contact": _privacy_contact(),
        },
    )


def _handle_user_export(claims: dict[str, Any]) -> dict[str, Any]:
    """The DPDP right of access: a machine-readable copy of the user's data."""
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    storage = _storage()

    kbs = kb_repo.list_kbs(sub)
    documents: list[dict[str, Any]] = []
    for kb in kbs:
        kb_id = str(kb.get("kbId") or kb.get("id") or "")
        if kb_id:
            documents.extend(_public_item(doc) for doc in documents_repo.list_documents(kb_id))

    storage_files: list[dict[str, Any]] = []
    for item in storage_repo.list_files(sub):
        entry = _public_item(item)
        key = item.get("s3Key")
        if key:
            try:
                entry["downloadUrl"] = storage.presign_get(str(key), PRESIGN_EXPIRES_SECONDS)
            except Exception:  # noqa: BLE001 - a missing object must not fail export
                entry["downloadUrl"] = None
        storage_files.append(entry)

    custom_servers: list[dict[str, Any]] = []
    for server in custom_tools_repo.list_servers(sub):
        entry = _public_item(server)
        entry["tools"] = [
            _public_item(tool)
            for tool in custom_tools_repo.list_tools(sub, str(server.get("slug") or ""))
        ]
        custom_servers.append(entry)

    conversations, _ = conversations_repo.list_conversations(sub, limit=100)
    playground_sessions, _ = playground_repo.list_sessions(sub, limit=100)
    eval_runs, _ = evals_repo.list_runs(sub, limit=100)

    budget = get_budget(sub)
    bundle: dict[str, Any] = {
        "exportedAt": now_iso(),
        "account": _public_item(profile),
        "consent": consent_repo.get_consent(sub),
        "settings": _public_item(settings_repo.get_settings(sub)),
        "notificationPreferences": _public_item(
            settings_repo.get_notification_preferences(sub)
        ),
        "budget": {
            "budgetCredits": core_usage.usd_to_credits(budget.budget_micro_usd),
            "spentCredits": core_usage.usd_to_credits(budget.spent_micro_usd),
        },
        "knowledgeBases": [_public_item(item) for item in kbs],
        "documents": documents,
        "agents": [_public_item(item) for item in agents_repo.list_agents(sub)],
        "workflows": [_public_item(item) for item in workflows_repo.list_workflows(sub)],
        "skills": [_public_item(item) for item in skills_repo.list_skills(sub)],
        "customServers": custom_servers,
        "storageFiles": storage_files,
        "vaultSecrets": [_public_item(item) for item in vault_repo.list_secrets(sub)],
        "conversations": [_public_item(item) for item in conversations],
        "playgroundSessions": [_public_item(item) for item in playground_sessions],
        "evaluationRuns": [_public_item(item) for item in eval_runs],
        "mcpConnections": [_public_item(item) for item in mcp_repo.list_connections(sub)],
        "notifications": [_public_item(item) for item in notifications_repo.list_notifications(sub)],
        "supportTickets": [_public_item(item) for item in support_repo.list_tickets(sub)],
        "contact": _privacy_contact(),
        "note": (
            "This is the personal data get1agent holds about you. Knowledge-base "
            "document contents are listed in 'documents'; the original files and "
            "your Storage files are downloadable via the presigned 'downloadUrl' "
            "links (valid for one hour)."
        ),
    }
    return _json(200, bundle)


def _delete_auth_user(sub: str) -> bool:
    """Best-effort removal of the Auth0 identity (needs Management API creds)."""
    domain = (
        os.environ.get("AUTH_DOMAIN")
        or os.environ.get("AUTH_ISSUER_BASE_URL")
        or os.environ.get("AUTH_ISSUER")
        or ""
    )
    client_id = os.environ.get("AUTH_MGMT_CLIENT_ID")
    client_secret = os.environ.get("AUTH_MGMT_CLIENT_SECRET")
    if not (domain and client_id and client_secret and sub):
        return False
    base = domain.rstrip("/")
    if not base.startswith("http"):
        base = f"https://{base}"
    try:
        from urllib.parse import urlencode

        token_body = urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "audience": f"{base}/api/v2/",
            }
        ).encode()
        token_request = urllib.request.Request(
            f"{base}/oauth/token", data=token_body, method="POST"
        )
        with urllib.request.urlopen(token_request, timeout=10) as response:
            token = json.loads(response.read().decode())["access_token"]
        delete_request = urllib.request.Request(
            f"{base}/api/v2/users/{quote(sub, safe='')}",
            method="DELETE",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(delete_request, timeout=10):
            return True
    except Exception as exc:  # noqa: BLE001 - identity removal is best-effort
        print(f"account delete: Auth0 removal failed for {sub}: {exc!r}", file=sys.stderr)
        return False


def _handle_user_account_delete(claims: dict[str, Any]) -> dict[str, Any]:
    """The DPDP right to erasure: erase every trace of the user's data."""
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    auth_sub = str(profile.get("sub") or claims.get("sub") or "")

    # 1) S3 objects — every prefix that can hold this user's data.
    storage = _storage()
    storage_objects = 0
    prefixes = [
        f"{layout.RAW_PREFIX}/{sub}/",
        f"{layout.DERIVED_PREFIX}/{sub}/",
        f"{layout.INDEX_PREFIX}/{sub}/",
        f"{layout.STORAGE_PREFIX}/{sub}/",
        f"{layout.CONVERSATION_PREFIX}/{sub}/",
        f"{layout.CUSTOM_PREFIX}/{sub}/",
        f"{layout.PLAYGROUND_PREFIX}/{sub}/",
        f"{layout.EVAL_PREFIX}/{sub}/",
        layout.mcp_prefix(sub),
        layout.agent_sessions_prefix(sub),
        layout.trace_prefix(sub),
    ]
    try:
        for prefix in prefixes:
            keys = storage.list_keys(prefix)
            if keys:
                storage.delete_many(keys)
                storage_objects += len(keys)
    except Exception as exc:  # noqa: BLE001 - never block the erasure
        print(f"account delete: S3 cleanup failed for {sub}: {exc!r}", file=sys.stderr)

    # 2) Semantic index (S3 Vectors or the local vector store).
    vectors_cleared = False
    try:
        vector_store(storage).delete_user(sub)
        vectors_cleared = True
    except Exception as exc:  # noqa: BLE001
        print(f"account delete: vector cleanup failed for {sub}: {exc!r}", file=sys.stderr)

    # 3) DynamoDB items (user partition + eval/support partitions).
    deleted = delete_user_data(sub)

    # 4) The sub -> userId identity binding, so a later login starts clean.
    delete_identity(auth_sub)

    # 5) Auth0 identity (best-effort; documented when creds are absent).
    auth_removed = _delete_auth_user(auth_sub)

    # 6) Evaluation Lab data (best-effort; datasets/cases/queues).
    lab_items = _delete_lab_data(sub)

    return _json(
        200,
        {
            "deletedAt": now_iso(),
            "storageObjects": storage_objects,
            "vectorsCleared": vectors_cleared,
            "dynamodb": deleted,
            "auth0IdentityRemoved": auth_removed,
            "labItemsDeleted": lab_items,
            "message": (
                "Your account and personal data have been erased. If Auth0 identity "
                "removal is not configured, contact the grievance officer to complete it."
            ),
            "contact": _privacy_contact(),
        },
    )


def _grievance_payload(ticket: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticketId": ticket.get("ticketId"),
        "subject": ticket.get("subject"),
        "requestType": ticket.get("requestType"),
        "status": ticket.get("status"),
        "createdAt": ticket.get("createdAt"),
        "updatedAt": ticket.get("updatedAt"),
        "messageCount": int(ticket.get("messageCount") or 0),
    }


def _handle_grievance_list(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    tickets = [
        _grievance_payload(item)
        for item in support_repo.list_tickets(profile["userId"])
        if item.get("kind") == support_repo.KIND_GRIEVANCE
    ]
    return _json(200, {"grievances": tickets, "contact": _privacy_contact()})


def _handle_grievance_create(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    subject = str(body.get("subject") or "").strip()
    message = str(body.get("message") or "").strip()
    request_type = str(body.get("requestType") or "other").strip()
    if request_type not in REQUEST_TYPES:
        request_type = "other"
    if not subject:
        raise ApiError(400, "Subject is required")
    if len(subject) > support_repo.MAX_SUBJECT:
        raise ApiError(400, f"Subject must be at most {support_repo.MAX_SUBJECT} characters")
    if not message:
        raise ApiError(400, "Please describe your request")
    if len(message) > support_repo.MAX_BODY:
        raise ApiError(400, f"Message must be at most {support_repo.MAX_BODY} characters")
    ticket = support_repo.create_ticket(
        profile["userId"],
        user_email=str(profile.get("email") or ""),
        subject=f"[Data rights] {subject}",
        body=message,
        kind=support_repo.KIND_GRIEVANCE,
        request_type=request_type,
    )
    return _json(
        201,
        {
            "grievance": _grievance_payload(ticket),
            "contact": _privacy_contact(),
            "message": (
                f"Your request has been logged. We aim to respond within "
                f"{GRIEVANCE_RESPONSE_DAYS} days."
            ),
        },
    )


# --- workflows ---------------------------------------------------------------


def _serialize_workflow(
    item: dict[str, Any], *, include_config: bool = False
) -> dict[str, Any]:
    config = item.get("config") or {}
    nodes = config.get("nodes") or []
    agent_ids = [
        str(node.get("data", {}).get("agentId"))
        for node in nodes
        if isinstance(node, dict)
        and node.get("type") == "agent"
        and isinstance(node.get("data"), dict)
        and node.get("data", {}).get("agentId")
    ]
    payload: dict[str, Any] = {
        "id": item["workflowId"],
        "name": item.get("name"),
        "description": item.get("description"),
        "status": item.get("status"),
        "mode": config.get("mode") or item.get("mode") or "graph",
        "version": int(item.get("version") or 1),
        "agentCount": int(item.get("agentCount") or len(agent_ids)),
        "agentIds": agent_ids,
        "nodeCount": len(nodes),
        "schedule": config.get("schedule"),
        "verifiedAt": item.get("verifiedAt"),
        "lastRunAt": item.get("lastRunAt"),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }
    if include_config:
        payload["config"] = config
    return payload


def _validated_workflow_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "Workflow name is required")
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


def _validated_workflow_description(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "Workflow description is required")
    description = value.strip()
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ApiError(400, f"description must be at most {MAX_DESCRIPTION_LENGTH} characters")
    return description


def _validated_workflow_overrides(value: Any) -> dict[str, Any]:
    """Per-workflow overrides for a referenced agent (only changed fields)."""
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise ApiError(400, "node.data.overrides must be an object")
    overrides: dict[str, Any] = {}
    if value.get("model") not in (None, ""):
        overrides["model"] = _validated_model(
            value.get("model"), SUPPORTED_AGENT_MODELS, "override model", SUPPORTED_AGENT_MODELS[0]
        )
    if "prompt" in value and value.get("prompt") is not None:
        prompt = value.get("prompt")
        if not isinstance(prompt, str):
            raise ApiError(400, "override prompt must be a string")
        if len(prompt) > MAX_AGENT_PROMPT_LENGTH:
            raise ApiError(400, f"override prompt must be at most {MAX_AGENT_PROMPT_LENGTH} characters")
        overrides["prompt"] = prompt
    if value.get("reasoning") not in (None, ""):
        overrides["reasoning"] = _validated_enum(
            value.get("reasoning"), AGENT_REASONING_LEVELS, "override reasoning", "medium"
        )
    if "servers" in value and value.get("servers") is not None:
        overrides["servers"] = _validated_agent_servers(value.get("servers"))
    if "skillIds" in value and value.get("skillIds") is not None:
        overrides["skillIds"] = _validated_id_list(value.get("skillIds"), "override skillIds")
    return overrides


def _validated_workflow_position(value: Any) -> dict[str, int]:
    # DynamoDB has no float type, so canvas coordinates are rounded to whole
    # pixels (sub-pixel precision is irrelevant for a saved layout).
    if not isinstance(value, dict):
        return {"x": 0, "y": 0}
    try:
        x = int(round(float(value.get("x") or 0)))
        y = int(round(float(value.get("y") or 0)))
    except (TypeError, ValueError):
        return {"x": 0, "y": 0}
    return {"x": x, "y": y}


def _validated_workflow_node_data(kind: str, value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    if kind == "agent":
        agent_id = str(data.get("agentId") or "").strip()
        try:
            agent_id = str(uuid.UUID(agent_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ApiError(400, "Every agent node needs a valid agentId") from exc
        return {
            "agentId": agent_id,
            "agentName": str(data.get("agentName") or "")[:AGENT_NAME_MAX],
            "overrides": _validated_workflow_overrides(data.get("overrides")),
        }
    if kind == "input":
        # The input card is the workflow's host agent: a starting query, the
        # workflow system prompt and the host's model.
        query = str(data.get("query") or "")
        prompt = str(data.get("prompt") or "")
        if len(query) > MAX_AGENT_PROMPT_LENGTH:
            raise ApiError(400, "input query is too long")
        if len(prompt) > MAX_AGENT_PROMPT_LENGTH:
            raise ApiError(400, "host system prompt is too long")
        return {
            "query": query,
            "prompt": prompt,
            "model": _validated_model(
                data.get("model"), SUPPORTED_AGENT_MODELS, "host model", SUPPORTED_AGENT_MODELS[0]
            ),
            "guardrail": _validated_guardrail(data.get("guardrail")),
        }
    if kind == "schedule":
        return _validated_schedule(data)
    # output
    instructions = str(data.get("instructions") or "")
    if len(instructions) > MAX_AGENT_PROMPT_LENGTH:
        raise ApiError(400, "output instructions are too long")
    return {
        "format": _validated_enum(
            data.get("format"), AGENT_OUTPUT_FORMATS, "output.format", "markdown"
        ),
        "instructions": instructions,
    }


def _validated_workflow_graph(value: Any) -> dict[str, Any]:
    if value in (None, {}):
        return {"nodes": [], "edges": []}
    if not isinstance(value, dict):
        raise ApiError(400, "config must be an object")
    raw_nodes = value.get("nodes") or []
    raw_edges = value.get("edges") or []
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise ApiError(400, "workflow nodes and edges must be lists")
    if len(raw_nodes) > MAX_WORKFLOW_NODES:
        raise ApiError(400, f"At most {MAX_WORKFLOW_NODES} nodes per workflow")
    if len(raw_edges) > MAX_WORKFLOW_EDGES:
        raise ApiError(400, f"At most {MAX_WORKFLOW_EDGES} edges per workflow")

    node_ids: set[str] = set()
    agent_ids: list[str] = []
    clean_nodes: list[dict[str, Any]] = []
    for node in raw_nodes:
        if not isinstance(node, dict):
            raise ApiError(400, "Each node must be an object")
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            raise ApiError(400, "Every node needs an id")
        if node_id in node_ids:
            raise ApiError(400, f"Duplicate node id: {node_id}")
        node_ids.add(node_id)
        kind = str(node.get("type") or "").strip().lower()
        if kind not in WORKFLOW_NODE_KINDS:
            raise ApiError(400, f"Node type must be one of {list(WORKFLOW_NODE_KINDS)}")
        data = _validated_workflow_node_data(kind, node.get("data"))
        if kind == "agent":
            agent_ids.append(data["agentId"])
        clean_nodes.append(
            {
                "id": node_id[:64],
                "type": kind,
                "position": _validated_workflow_position(node.get("position")),
                "data": data,
            }
        )
    if len(agent_ids) > MAX_WORKFLOW_AGENTS:
        raise ApiError(400, f"At most {MAX_WORKFLOW_AGENTS} agents per workflow")

    edge_ids: set[str] = set()
    clean_edges: list[dict[str, Any]] = []
    for edge in raw_edges:
        if not isinstance(edge, dict):
            raise ApiError(400, "Each edge must be an object")
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in node_ids or target not in node_ids:
            raise ApiError(400, "Every edge must connect two existing nodes")
        if source == target:
            raise ApiError(400, "An edge cannot connect a node to itself")
        edge_id = str(edge.get("id") or f"e-{source}-{target}")
        if edge_id in edge_ids:
            continue
        edge_ids.add(edge_id)
        clean_edges.append({"id": edge_id[:128], "source": source, "target": target})
    return {"nodes": clean_nodes, "edges": clean_edges}


def _validated_workflow_config(value: Any) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ApiError(400, "config must be an object")

    mode = _validated_enum(value.get("mode"), WORKFLOW_MODES, "mode", "graph")
    graph = _validated_workflow_graph(value)
    nodes = graph["nodes"]
    agent_node_ids = [node["id"] for node in nodes if node["type"] == "agent"]
    input_nodes = [node for node in nodes if node["type"] == "input"]
    output_nodes = [node for node in nodes if node["type"] == "output"]
    schedule_nodes = [node for node in nodes if node["type"] == "schedule"]
    if len(input_nodes) != 1:
        raise ApiError(400, "A workflow needs exactly one input node")
    if len(output_nodes) != 1:
        raise ApiError(400, "A workflow needs exactly one output node")
    if len(schedule_nodes) > 1:
        raise ApiError(400, "A workflow can have at most one schedule node")
    if not agent_node_ids:
        raise ApiError(400, "Add at least one agent to the workflow")

    input_data = input_nodes[0]["data"]
    output_data = output_nodes[0]["data"]
    schedule_data = (
        schedule_nodes[0]["data"]
        if schedule_nodes
        else {"enabled": False, "cron": "", "timezone": "UTC"}
    )
    version = value.get("version")
    if not isinstance(version, int) or version < 1:
        version = WORKFLOW_CONFIG_VERSION

    config: dict[str, Any] = {
        "version": version,
        "mode": mode,
        "input": {
            "query": str(input_data.get("query") or ""),
            "prompt": str(input_data.get("prompt") or ""),
            "model": str(input_data.get("model") or SUPPORTED_AGENT_MODELS[0]),
        },
        "output": {
            "format": str(output_data.get("format") or "markdown"),
            "instructions": str(output_data.get("instructions") or ""),
        },
        "schedule": _validated_schedule(schedule_data),
        "guardrail": _validated_guardrail(
            value.get("guardrail") or (input_data.get("guardrail") if isinstance(input_data, dict) else None)
        ),
        "nodes": nodes,
        "edges": graph["edges"],
    }
    if len(json_dumps(config).encode("utf-8")) > MAX_WORKFLOW_CONFIG_BYTES:
        raise ApiError(413, "Workflow configuration is too large")
    return config


def _workflow_validation(sub: str, item: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Dry-run checks: structure + every referenced agent still exists."""
    errors: list[str] = []
    warnings: list[str] = []
    config = item.get("config") or {}
    nodes = [node for node in config.get("nodes") or [] if isinstance(node, dict)]
    agent_nodes = [node for node in nodes if node.get("type") == "agent"]
    if not agent_nodes:
        errors.append("Add at least one agent to the workflow.")

    if not str((config.get("input") or {}).get("prompt") or "").strip():
        warnings.append("The host has no system prompt; a default one will be used.")

    seen_agents: set[str] = set()
    for node in agent_nodes:
        data = node.get("data") or {}
        agent_id = str(data.get("agentId") or "")
        if not agent_id:
            errors.append("An agent node has no agent selected.")
            continue
        seen_agents.add(agent_id)
        agent = agents_repo.get_agent(sub, agent_id)
        if agent is None:
            errors.append(f'Agent "{data.get("agentName") or agent_id}" no longer exists.')
            continue
        agent_config = agent.get("config") or {}
        overrides = data.get("overrides") or {}
        for kb_id in agent_config.get("knowledgeBaseIds") or []:
            kb = kb_repo.get_kb(sub, kb_id)
            if kb is None:
                errors.append(f'Agent "{agent.get("name")}" references a knowledge base that no longer exists.')
            elif kb.get("status") != "ready":
                warnings.append(f'Knowledge base "{kb.get("name")}" is still {kb.get("status")}.')
        servers = overrides.get("servers", agent_config.get("servers")) or []
        for server in servers:
            server_id = server.get("id")
            if server_id in BUILTIN_AGENT_SERVERS:
                continue
            connection = mcp_repo.get_connection(sub, server_id)
            if connection is None:
                errors.append(f'MCP server {server_id} is not connected.')
            elif connection.get("enabled") is False:
                errors.append(f'MCP server "{connection.get("name")}" is disabled.')

    if len(seen_agents) < len(agent_nodes):
        warnings.append("Some agents are attached more than once.")

    return errors, warnings


def _get_workflow_or_404(sub: str, workflow_id: str) -> dict[str, Any]:
    workflow = workflows_repo.get_workflow(sub, workflow_id)
    if workflow is None:
        raise ApiError(404, "Workflow not found")
    return workflow


def _handle_workflow_list(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    rows = workflows_repo.list_workflows(sub)
    return _json(
        200,
        {
            "workflows": [_serialize_workflow(workflow) for workflow in rows],
            "usage": {
                "workflows": len(rows),
                "limits": {"workflows": MAX_WORKFLOWS_PER_USER},
            },
        },
    )


def _handle_workflow_create(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    if workflows_repo.count_workflows(sub) >= MAX_WORKFLOWS_PER_USER:
        raise ApiError(409, f"You can create at most {MAX_WORKFLOWS_PER_USER} workflows")
    name = _validated_workflow_name(body.get("name"))
    try:
        workflow = workflows_repo.create_workflow(
            sub,
            workflow_id=str(uuid.uuid4()),
            name=name,
            description=_validated_workflow_description(body.get("description")),
            config=_validated_workflow_config(body.get("config")),
        )
    except DuplicateWorkflow as exc:
        raise ApiError(409, f'A workflow named "{name}" already exists') from exc
    _sync_schedule(sub, "workflow", str(workflow["workflowId"]), str(workflow.get("name") or name), workflow.get("config") or {})
    return _json(201, _serialize_workflow(workflow, include_config=True))


def _handle_workflow_detail(claims: dict[str, Any], workflow_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    workflow = _get_workflow_or_404(profile["userId"], workflow_id)
    return _json(200, _serialize_workflow(workflow, include_config=True))


def _handle_workflow_update(
    claims: dict[str, Any], workflow_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    _get_workflow_or_404(sub, workflow_id)
    name = _validated_workflow_name(body.get("name"))
    try:
        workflow = workflows_repo.update_workflow(
            sub,
            workflow_id,
            name=name,
            description=_validated_workflow_description(body.get("description")),
            config=_validated_workflow_config(body.get("config")),
        )
    except DuplicateWorkflow as exc:
        raise ApiError(409, f'A workflow named "{name}" already exists') from exc
    if workflow is None:
        raise ApiError(404, "Workflow not found")
    _sync_schedule(sub, "workflow", workflow_id, str(workflow.get("name") or name), workflow.get("config") or {})
    return _json(200, _serialize_workflow(workflow, include_config=True))


def _handle_workflow_delete(claims: dict[str, Any], workflow_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    _get_workflow_or_404(sub, workflow_id)
    workflows_repo.delete_workflow(sub, workflow_id)
    _clear_schedule(sub, "workflow", workflow_id)
    return _json(200, {"ok": True})


def _handle_workflow_verify(claims: dict[str, Any], workflow_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    workflow = _get_workflow_or_404(sub, workflow_id)
    errors, warnings = _workflow_validation(sub, workflow)
    if errors:
        return _json(
            200,
            {
                "valid": False,
                "errors": errors,
                "warnings": warnings,
                "workflow": _serialize_workflow(workflow, include_config=True),
            },
        )
    workflows_repo.mark_verified(sub, workflow_id, verified_at=now_iso())
    updated = _get_workflow_or_404(sub, workflow_id)
    return _json(
        200,
        {
            "valid": True,
            "errors": [],
            "warnings": warnings,
            "workflow": _serialize_workflow(updated, include_config=True),
        },
    )


def _handle_workflow_runs(
    claims: dict[str, Any], workflow_id: str, query: dict[str, str]
) -> dict[str, Any]:
    """List a user's conversations for one workflow (builder history)."""
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    workflow_id = _parse_id(workflow_id, "Workflow")
    if workflows_repo.get_workflow(sub, workflow_id) is None:
        raise ApiError(404, "Workflow not found")
    try:
        limit = int(query.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(100, limit))
    items, next_key = conversations_repo.list_conversations_for_agent(sub, workflow_id, limit)
    return _json(
        200,
        {
            "runs": [_serialize_conversation(item, sub) for item in items],
            "nextCursor": _encode_cursor(next_key),
        },
    )


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


# --- public trace links (signed + expiring) ----------------------------------
#
# The agent runtime exports each run's spans to CloudWatch/X-Ray and stores the
# trace id on the turn. We sign that id into a short-lived link that our own
# endpoint verifies and redirects through, so the link we surface expires.

TRACE_LINK_TTL_SECONDS = 1800


def _trace_link_secret() -> str:
    return (os.environ.get("TRACE_LINK_SECRET") or "").strip()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _trace_token(
    trace_id: str | None,
    user_id: str | None = None,
    conversation_id: str | int | None = None,
) -> str | None:
    """Sign a trace (plus its conversation + owner) into an expiring token."""
    secret = _trace_link_secret()
    if not secret or not trace_id:
        return None
    data: dict[str, Any] = {
        "t": str(trace_id),
        "r": os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "ap-south-1",
        "e": int(time.time()) + TRACE_LINK_TTL_SECONDS,
    }
    if user_id:
        data["u"] = str(user_id)
    if conversation_id is not None:
        data["c"] = str(conversation_id)
    payload = _b64url_encode(json.dumps(data).encode())
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{_b64url_encode(signature)}"


def _trace_payload(token: str) -> dict[str, Any] | None:
    """Verify a trace token and return its payload (None when invalid/expired)."""
    secret = _trace_link_secret()
    if not secret or not token or "." not in token:
        return None
    payload, _, signature = token.partition(".")
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    try:
        provided = _b64url_decode(signature)
    except Exception:  # noqa: BLE001 - malformed token
        return None
    if not hmac.compare_digest(expected, provided):
        return None
    try:
        data = json.loads(_b64url_decode(payload))
        trace_id = str(data.get("t") or "")
        expires = int(data.get("e") or 0)
    except Exception:  # noqa: BLE001 - malformed payload
        return None
    if not trace_id or expires < int(time.time()):
        return None
    return {
        "traceId": trace_id,
        "region": str(data.get("r") or "ap-south-1"),
        "userId": str(data.get("u") or ""),
        "conversationId": str(data.get("c") or ""),
    }


def _trace_link(
    trace_id: str | None,
    user_id: str | None = None,
    conversation_id: str | int | None = None,
) -> str | None:
    """A relative, signed, 30-minute public link to the in-app trace page."""
    token = _trace_token(trace_id, user_id, conversation_id)
    return f"/trace/{token}" if token else None


def _handle_trace(token: str) -> dict[str, Any]:
    """Public: return a run's full trace for the public trace viewer.

    The token is signed and bound to the owner, so the holder can read exactly
    that one run. The trace is served from the app's own store (X-Ray is only a
    transparent fallback on the server); the viewer never touches AWS.
    """
    payload = _trace_payload(token)
    if not payload:
        return _json(410, {"error": "This trace link has expired."})

    user_id = payload.get("userId") or ""
    conversation_id = payload.get("conversationId") or ""
    trace = None
    try:
        if user_id:
            trace = lab_store.read_trace(user_id, payload["traceId"])
    except Exception:  # noqa: BLE001 - missing trace still renders a shell
        trace = None

    return _json(
        200,
        {
            "traceId": payload["traceId"],
            "conversationId": conversation_id,
            "region": payload["region"],
            "trace": trace,
        },
    )


def _serialize_conversation(item: dict[str, Any], sub: str | None = None) -> dict[str, Any]:
    return {
        "conversationId": int(item.get("conversationId") or 0),
        "agentId": item.get("agentId"),
        "agentName": item.get("agentName"),
        "targetType": item.get("targetType") or conversations_repo.TARGET_AGENT,
        "kind": item.get("kind") or conversations_repo.KIND_CHAT,
        "title": item.get("title") or "",
        "lastPreview": item.get("lastPreview") or "",
        "messageCount": int(item.get("messageCount") or 0),
        "runCount": int(item.get("runCount") or 0),
        "lastRunId": item.get("lastRunId"),
        "lastTraceId": item.get("lastTraceId"),
        "lastTraceUrl": _trace_link(item.get("lastTraceId"), sub, item.get("conversationId")),
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
    target_type = str(body.get("targetType") or conversations_repo.TARGET_AGENT).strip().lower()
    if target_type not in conversations_repo.TARGETS:
        raise ApiError(400, "targetType must be 'agent' or 'workflow'")
    target_id = _parse_id(str(body.get("agentId") or ""), "Target")
    if target_type == conversations_repo.TARGET_WORKFLOW:
        target = workflows_repo.get_workflow(sub, target_id)
        if target is None:
            raise ApiError(404, "Workflow not found")
    else:
        target = agents_repo.get_agent(sub, target_id)
        if target is None:
            raise ApiError(404, "Agent not found")
    kind = str(body.get("kind") or conversations_repo.KIND_CHAT).strip().lower()
    if kind not in conversations_repo.KINDS:
        raise ApiError(400, "kind must be 'chat' or 'run'")
    title = str(body.get("title") or "").strip()[:MAX_CONVERSATION_TITLE]
    item = conversations_repo.create_conversation(
        user_id=sub,
        agent_id=target_id,
        agent_name=str(target.get("name") or ""),
        kind=kind,
        title=title,
        target_type=target_type,
    )
    # A freshly minted id must not inherit a stale transcript. Conversation ids
    # come from one monotonic counter, but a local counter reset (DynamoDB
    # volume recreated while S3 persists) can hand out an id whose transcript
    # object still exists; clearing it keeps the new conversation empty.
    try:
        _storage().delete(layout.conversation_key(sub, int(item["conversationId"])))
    except Exception:  # noqa: BLE001 - best-effort cleanup
        pass
    return _json(201, _serialize_conversation(item, sub))


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
            "conversations": [_serialize_conversation(item, sub) for item in items],
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
    turns = _load_transcript(sub, conversation_id)
    feedback = feedback_repo.get_feedback_many(
        sub,
        [str(turn.get("runId") or "") for turn in turns if isinstance(turn, dict)],
    )
    for turn in turns:
        if isinstance(turn, dict):
            # Swap the stored trace id for a fresh signed public link.
            turn["traceUrl"] = _trace_link(
                turn.get("traceId") or turn.get("lastTraceId"), sub, conversation_id
            )
            turn["feedback"] = _serialize_feedback(
                feedback.get(str(turn.get("runId") or ""))
            )
    return _json(
        200,
        {
            "conversation": _serialize_conversation(item, sub),
            "turns": turns,
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
    return _json(200, _serialize_conversation(updated or item, sub))


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
    feedback = feedback_repo.get_feedback_many(
        sub, [str(item.get("lastRunId") or "") for item in items]
    )
    runs: list[dict[str, Any]] = []
    for item in items:
        data = _serialize_conversation(item, sub)
        data["feedback"] = _serialize_feedback(feedback.get(str(item.get("lastRunId") or "")))
        runs.append(data)
    return _json(
        200,
        {
            "runs": runs,
            "nextCursor": _encode_cursor(next_key),
        },
    )


# --- run feedback ------------------------------------------------------------

MAX_FEEDBACK_COMMENT = 2000


def _serialize_feedback(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    return {
        "runId": item.get("runId"),
        "value": item.get("value"),
        "comment": item.get("comment") or "",
        "categories": item.get("categories") or [],
        "updatedAt": item.get("updatedAt"),
    }


def _emit_feedback_metric(agent_id: str | None, value: str) -> None:
    """Emit run feedback as a CloudWatch EMF metric (no custom-metric API call)."""
    try:
        payload = {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": "get1agent/feedback",
                        "Dimensions": [["agentId", "sentiment"]],
                        "Metrics": [{"Name": "RunFeedback", "Unit": "Count"}],
                    }
                ],
            },
            "agentId": str(agent_id or "unknown"),
            "sentiment": "up" if value == feedback_repo.VALUE_UP else "down",
            "RunFeedback": 1,
        }
        print(json_dumps(payload), flush=True)
    except Exception:  # noqa: BLE001 - metrics must never fail the request
        pass


def _delete_lab_data(user_id: str) -> int:
    """Erase the user's Lab data (datasets, cases, queues) on account closure.

    Deletes the caller's AWS-native Lab data (datasets, cases, queues).
    the DynamoDB-backed Lab items. Failures are logged, never blocking erasure.
    """
    try:
        return lab_store.delete_user(user_id)
    except Exception as exc:  # noqa: BLE001 - erasure must not fail on cleanup
        print(f"account delete: Lab cleanup failed for {user_id}: {exc!r}", file=sys.stderr)
        return 0


def _handle_feedback_put(
    claims: dict[str, Any], run_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    run_id = str(run_id or "").strip()[:128]
    if not run_id:
        raise ApiError(400, "runId is required")

    trace_id = str(body.get("traceId") or "").strip() or None
    value = str(body.get("value") or "").strip().lower()
    comment = str(body.get("comment") or "").strip()[:MAX_FEEDBACK_COMMENT]
    raw_categories = body.get("categories")
    categories: list[str] = []
    if isinstance(raw_categories, list):
        categories = [str(c).strip()[:60] for c in raw_categories if str(c).strip()][
            : feedback_repo.MAX_CATEGORIES
        ]

    if not value:
        # No sentiment selected: clear the feedback (thumbs toggled off).
        feedback_repo.delete_feedback(sub, run_id)
        return _json(
            200,
            {
                "feedback": {
                    "runId": run_id,
                    "value": None,
                    "comment": "",
                    "categories": [],
                }
            },
        )
    if value not in feedback_repo.VALUES:
        raise ApiError(400, "value must be 'up' or 'down'")

    conversation_id = body.get("conversationId")
    try:
        conversation_id = int(conversation_id) if conversation_id is not None else None
    except (TypeError, ValueError):
        conversation_id = None

    item = feedback_repo.upsert_feedback(
        sub,
        run_id,
        value=value,
        comment=comment,
        categories=categories,
        trace_id=trace_id,
        conversation_id=conversation_id,
        agent_id=str(body.get("agentId") or "").strip() or None,
    )
    if trace_id:
        _emit_feedback_metric(str(body.get("agentId") or "").strip() or None, value)
    return _json(200, {"feedback": _serialize_feedback(item)})



# --- evaluation lab ----------------------------------------------------------
#
# RAG offline evaluation. A dataset (golden cases) is owned by the user; a run
# captures the retrieval/generation config plus aggregate metrics, and each
# per-case result is a tiny item whose bulky artifact (contexts, answer, judge
# reasoning) lives in S3. A run executes in a background invocation of this
# function (like the Playground turn) so it outlives API Gateway's 30s cap.

_EVAL_HIDDEN_KEYS = {
    "pk",
    "sk",
    "gsi1pk",
    "gsi1sk",
    "gsi2pk",
    "gsi2sk",
    "gsi3pk",
    "gsi3sk",
    "entity",
    "userId",
}


def _eval_item(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {key: value for key, value in item.items() if key not in _EVAL_HIDDEN_KEYS}


def _eval_name(body: dict[str, Any]) -> str:
    name = str(body.get("name") or "").strip()
    if not name:
        raise ApiError(400, "Name is required")
    if len(name) > evals_config.MAX_EVAL_NAME_CHARS:
        raise ApiError(400, "Name is too long")
    return name


def _eval_description(body: dict[str, Any]) -> str:
    return str(body.get("description") or "").strip()[
        : evals_config.MAX_EVAL_DESCRIPTION_CHARS
    ]


def _eval_expected_sources(body: dict[str, Any]) -> list[dict[str, Any]]:
    raw = body.get("expectedSources")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ApiError(400, "expectedSources must be a list")
    sources: list[dict[str, Any]] = []
    for entry in raw[: evals_config.MAX_EVAL_EXPECTED_SOURCES]:
        if not isinstance(entry, dict):
            continue
        document_id = str(entry.get("documentId") or "").strip()
        if not document_id:
            continue
        page = entry.get("page")
        try:
            page = int(page) if page not in (None, "") else None
        except (TypeError, ValueError):
            page = None
        sources.append({"documentId": document_id, "page": page})
    return sources


def _eval_case_fields(body: dict[str, Any]) -> dict[str, Any]:
    query = str(body.get("query") or "").strip()
    if not query:
        raise ApiError(400, "Each case needs a query")
    if len(query) > evals_config.MAX_EVAL_QUERY_CHARS:
        raise ApiError(400, "Query is too long")
    metadata = body.get("metadata")
    return {
        "query": query,
        "expected_output": str(body.get("expectedOutput") or "").strip()[
            : evals_config.MAX_EVAL_EXPECTED_OUTPUT_CHARS
        ],
        "expected_sources": _eval_expected_sources(body),
        "metadata": metadata if isinstance(metadata, dict) else {},
    }


def _eval_config(body: dict[str, Any]) -> dict[str, Any]:
    raw = body.get("config")
    if not isinstance(raw, dict):
        raw = {}
    mode = str(raw.get("mode") or evals_config.DEFAULT_MODE).strip().lower()
    if mode not in evals_config.MODES:
        raise ApiError(400, "mode must be 'rag' or 'retrieval'")
    task = str(raw.get("task") or evals_config.DEFAULT_TASK).strip().lower()
    if task not in evals_config.TASKS:
        raise ApiError(400, "task must be 'rag' or 'agent'")
    config: dict[str, Any] = {"mode": mode, "rerank": bool(raw.get("rerank")), "task": task}
    if task == evals_config.TASK_AGENT:
        agent_id = str(raw.get("agentId") or "").strip()
        if not agent_id:
            raise ApiError(400, "Select an agent to evaluate")
        config["agentId"] = agent_id
    return config


def _eval_kb_names(body: dict[str, Any]) -> list[str]:
    raw = body.get("knowledgeBaseNames")
    if not isinstance(raw, list):
        raise ApiError(400, "Select at least one knowledge base")
    names: list[str] = []
    for value in raw[: evals_config.MAX_EVAL_KB_NAMES]:
        name = str(value or "").strip()
        if name:
            names.append(name)
    if not names:
        raise ApiError(400, "Select at least one knowledge base")
    return names


def _eval_optional_kb_names(body: dict[str, Any]) -> list[str]:
    """Knowledge bases are optional for agent runs (the agent has its own)."""
    raw = body.get("knowledgeBaseNames")
    if not isinstance(raw, list):
        return []
    return [str(value).strip() for value in raw[: evals_config.MAX_EVAL_KB_NAMES] if str(value).strip()]


def _route_evals(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
    query: dict[str, str],
):
    if not rest:
        raise ApiError(404, "Not found")
    if rest[0] == "datasets":
        return _route_eval_datasets(claims, method, rest[1:], body)
    if rest[0] == "runs":
        return _route_eval_runs(claims, method, rest[1:], body)
    raise ApiError(404, "Not found")


_EVAL_DATASET_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


def _eval_dataset_name(value: str) -> str:
    name = (value or "").strip().lower()
    if not name or len(name) > 48 or not _EVAL_DATASET_NAME_RE.match(name):
        raise ApiError(
            400, "Dataset names are lowercase letters, digits and hyphens"
        )
    return name


def _eval_require_lab_store() -> None:
    if not lab_store.configured():
        raise ApiError(503, "The Lab store is not configured")


def _eval_lf_dataset(sub: str, item: dict[str, Any]) -> dict[str, Any]:
    name = lab_store.display_name(sub, str(item.get("name") or ""))
    count = item.get("itemCount")
    return {
        "datasetId": name,
        "name": name,
        "description": str(item.get("description") or ""),
        "caseCount": int(count) if isinstance(count, (int, float)) else None,
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }


def _eval_lf_case(item: dict[str, Any]) -> dict[str, Any]:
    parsed = evals_runner.case_from_item(item)
    return {
        "caseId": str(item.get("id") or ""),
        "datasetId": "",
        "query": parsed["query"],
        "expectedOutput": parsed["expectedOutput"],
        "expectedSources": parsed["expectedSources"],
        "sourceTraceId": item.get("sourceTraceId"),
        "metadata": parsed["metadata"],
        "createdAt": item.get("createdAt"),
    }


def _route_eval_datasets(
    claims: dict[str, Any], method: str, rest: list[str], body: dict[str, Any]
):
    if not rest:
        if method == "GET":
            return _handle_eval_datasets_list(claims)
        if method == "POST":
            return _handle_eval_dataset_create(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    name = _eval_dataset_name(rest[0])
    if len(rest) == 1:
        if method == "GET":
            return _handle_eval_dataset_detail(claims, name)
        if method == "DELETE":
            return _handle_eval_dataset_delete(claims, name)
        if method == "PUT":
            return _handle_eval_dataset_update(claims, name, body)
        raise ApiError(405, f"Method not allowed: {method}")

    if rest[1] == "cases":
        if len(rest) == 2:
            if method == "GET":
                return _handle_eval_cases_list(claims, name)
            if method == "POST":
                return _handle_eval_cases_add(claims, name, body)
            raise ApiError(405, f"Method not allowed: {method}")
        if len(rest) == 3 and method == "DELETE":
            return _handle_eval_case_delete(claims, name, rest[2])
        raise ApiError(404, "Not found")

    if rest[1] == "runs":
        if len(rest) == 2 and method == "GET":
            return _handle_eval_dataset_runs(claims, name)
        raise ApiError(404, "Not found")

    raise ApiError(404, "Not found")


def _route_eval_runs(
    claims: dict[str, Any], method: str, rest: list[str], body: dict[str, Any]
):
    if not rest:
        if method == "GET":
            return _handle_eval_runs_list(claims)
        if method == "POST":
            return _handle_eval_run_create(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    run_id = _parse_id(rest[0], "Run")
    if len(rest) == 1:
        if method == "GET":
            return _handle_eval_run_detail(claims, run_id)
        if method == "DELETE":
            return _handle_eval_run_delete(claims, run_id)
        raise ApiError(405, f"Method not allowed: {method}")

    if rest[1] == "cases":
        if len(rest) == 2 and method == "GET":
            return _handle_eval_run_cases(claims, run_id)
        if len(rest) == 3 and method == "GET":
            case_id = _parse_id(rest[2], "Case")
            return _handle_eval_run_case_detail(claims, run_id, case_id)
        raise ApiError(404, "Not found")

    raise ApiError(404, "Not found")


def _handle_eval_datasets_list(claims: dict[str, Any]) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    if not lab_store.configured():
        return _json(200, {"configured": False, "datasets": []})
    prefix = f"u_{sub}/"
    datasets = [
        _eval_lf_dataset(sub, item)
        for item in lab_store.list_datasets()
        if str(item.get("name") or "").startswith(prefix)
    ]
    return _json(200, {"configured": True, "datasets": datasets})


def _handle_eval_dataset_create(
    claims: dict[str, Any], body: dict[str, Any]
) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    _eval_require_lab_store()
    name = _eval_dataset_name(_eval_name(body))
    full = lab_store.full_name(sub, name)
    existing = {str(item.get("name") or "") for item in lab_store.list_datasets()}
    if full in existing:
        raise ApiError(409, f'A dataset named "{name}" already exists')
    mine = [entry for entry in existing if entry.startswith(f"u_{sub}/")]
    if len(mine) >= evals_config.MAX_EVAL_DATASETS_PER_USER:
        raise ApiError(
            400,
            f"You can have at most {evals_config.MAX_EVAL_DATASETS_PER_USER} datasets",
        )
    description = _eval_description(body)
    lab_store.create_dataset(full, description)
    return _json(
        201,
        {
            "dataset": {
                "datasetId": name,
                "name": name,
                "description": description,
                "caseCount": 0,
            }
        },
    )


def _handle_eval_dataset_detail(
    claims: dict[str, Any], name: str
) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    _eval_require_lab_store()
    full = lab_store.full_name(sub, name)
    try:
        dataset = lab_store.get_dataset(full)
        items = lab_store.list_dataset_items(full)
    except lab_store.StoreError as exc:
        raise ApiError(404, f"Dataset not found: {exc}") from exc
    payload = _eval_lf_dataset(
        sub, dataset if isinstance(dataset, dict) else {"name": full}
    )
    payload["caseCount"] = len(items)
    payload["cases"] = [_eval_lf_case(item) for item in items]
    return _json(200, {"dataset": payload})


def _handle_eval_dataset_update(
    claims: dict[str, Any], name: str, body: dict[str, Any]
) -> dict[str, Any]:
    raise ApiError(405, "Renaming a dataset is not supported")


def _handle_eval_dataset_delete(
    claims: dict[str, Any], name: str
) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    _eval_require_lab_store()
    try:
        lab_store.delete_dataset(lab_store.full_name(sub, name))
    except lab_store.StoreError as exc:
        raise ApiError(404, f"Dataset not found: {exc}") from exc
    return _json(200, {"ok": True})


def _handle_eval_cases_list(
    claims: dict[str, Any], name: str
) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    _eval_require_lab_store()
    full = lab_store.full_name(sub, name)
    try:
        items = lab_store.list_dataset_items(full)
    except lab_store.StoreError as exc:
        raise ApiError(404, f"Dataset not found: {exc}") from exc
    return _json(200, {"cases": [_eval_lf_case(item) for item in items]})


def _handle_eval_cases_add(
    claims: dict[str, Any], name: str, body: dict[str, Any]
) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    _eval_require_lab_store()
    full = lab_store.full_name(sub, name)

    # Create the dataset on demand (e.g. saving a Playground replay to a new one).
    try:
        lab_store.get_dataset(full)
    except lab_store.StoreError:
        try:
            lab_store.create_dataset(full, "")
        except lab_store.StoreError:
            pass

    raw = body.get("cases")
    entries = raw if isinstance(raw, list) else [body]
    if not entries:
        raise ApiError(400, "Add at least one case")

    try:
        existing = len(lab_store.list_dataset_items(full))
    except lab_store.StoreError:
        existing = 0
    room = evals_config.MAX_EVAL_CASES_PER_DATASET - existing
    if room <= 0:
        raise ApiError(
            400,
            f"A dataset can hold at most {evals_config.MAX_EVAL_CASES_PER_DATASET} cases",
        )

    created: list[dict[str, Any]] = []
    for entry in entries[:room]:
        if not isinstance(entry, dict):
            raise ApiError(400, "Each case must be an object")
        fields = _eval_case_fields(entry)
        metadata = dict(fields["metadata"])
        if fields["expected_sources"]:
            metadata["expectedSources"] = fields["expected_sources"]
        try:
            item = lab_store.create_dataset_item(
                dataset_name=full,
                input_value={"question": fields["query"]},
                expected_output=fields["expected_output"] or None,
                metadata=metadata or None,
            )
        except lab_store.StoreError as exc:
            raise ApiError(502, f"Could not add the case: {exc}") from exc
        created.append(_eval_lf_case(item if isinstance(item, dict) else {}))
    return _json(
        201,
        {"cases": created, "caseCount": existing + len(created)},
    )


def _handle_eval_case_delete(
    claims: dict[str, Any], name: str, case_id: str
) -> dict[str, Any]:
    get_or_create_user(claims)
    _eval_require_lab_store()
    try:
        lab_store.delete_dataset_item(case_id)
    except lab_store.StoreError as exc:
        raise ApiError(404, f"Case not found: {exc}") from exc
    return _json(200, {"ok": True})


def _handle_eval_dataset_runs(claims: dict[str, Any], name: str) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    _eval_require_lab_store()
    full = lab_store.full_name(sub, name)
    try:
        runs = lab_store.list_dataset_runs(full)
    except lab_store.StoreError as exc:
        raise ApiError(502, f"Could not load runs: {exc}") from exc
    return _json(
        200,
        {
            "runs": [
                {
                    "id": row.get("id"),
                    "name": str(row.get("name") or ""),
                    "description": str(row.get("description") or ""),
                    "createdAt": row.get("createdAt"),
                    "metadata": row.get("metadata") or {},
                }
                for row in runs
            ]
        },
    )


def _handle_eval_runs_list(claims: dict[str, Any]) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    items, _ = evals_repo.list_runs(sub, limit=100)
    return _json(200, {"runs": [_eval_item(item) for item in items]})


def _handle_eval_run_create(
    claims: dict[str, Any], body: dict[str, Any]
) -> dict[str, Any]:
    sub = _require_budget(claims)
    raw_name = str(body.get("datasetId") or "").strip()
    if not raw_name:
        raise ApiError(400, "Select a dataset")
    name = _eval_dataset_name(raw_name)
    _eval_require_lab_store()
    full = lab_store.full_name(sub, name)
    try:
        lab_store.get_dataset(full)
        items = lab_store.list_dataset_items(full)
    except lab_store.StoreError as exc:
        raise ApiError(404, f"Dataset not found: {exc}") from exc

    run_config = _eval_config(body)
    kb_names = (
        _eval_optional_kb_names(body)
        if run_config["task"] == evals_config.TASK_AGENT
        else _eval_kb_names(body)
    )
    if not evals_config.enabled():
        raise ApiError(400, "The evaluation model gateway is not configured")
    if run_config["task"] == evals_config.TASK_AGENT and not (
        evals_config.agent_run_function()
        and evals_config.service_client_id()
        and evals_config.service_client_secret()
        and evals_config.service_audience()
    ):
        raise ApiError(503, "Agent evaluation is not configured")
    if not items:
        raise ApiError(400, "Add cases to the dataset first")

    run = evals_repo.create_run(
        sub,
        dataset_id=name,
        dataset_name=name,
        knowledge_base_names=kb_names,
        config=run_config,
        case_count=len(items),
    )
    try:
        _invoke_self_async(
            {_ASYNC_ACTION: "evals.run", "userId": sub, "runId": run["runId"]}
        )
    except ApiError as exc:
        evals_repo.update_run(
            sub, run["runId"], status=evals_repo.RUN_FAILED, error=str(exc)
        )
        raise
    return _json(202, {"run": _eval_item(run)})


def _handle_eval_run_detail(claims: dict[str, Any], run_id: str) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    run = evals_repo.get_run(sub, run_id)
    if run is None:
        raise ApiError(404, "Run not found")
    payload = _eval_item(run) or {}
    payload["maxCases"] = evals_config.max_cases_per_run()
    return _json(200, {"run": payload})


def _handle_eval_run_delete(claims: dict[str, Any], run_id: str) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    if evals_repo.delete_run(sub, run_id) is None:
        raise ApiError(404, "Run not found")
    return _json(200, {"ok": True})


def _handle_eval_run_cases(claims: dict[str, Any], run_id: str) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    if evals_repo.get_run(sub, run_id) is None:
        raise ApiError(404, "Run not found")
    results, _ = evals_repo.list_case_results(sub, run_id, limit=500)
    return _json(200, {"cases": [_eval_item(result) for result in results]})


def _handle_eval_run_case_detail(
    claims: dict[str, Any], run_id: str, case_id: str
) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    if evals_repo.get_run(sub, run_id) is None:
        raise ApiError(404, "Run not found")
    result = evals_repo.get_case_result(sub, run_id, case_id)
    if result is None:
        raise ApiError(404, "Case result not found")
    artifact = None
    key = str(result.get("artifactKey") or "")
    if key:
        try:
            artifact = _storage().get_json(key)
        except Exception:  # noqa: BLE001 - artifact is best-effort
            artifact = None
    return _json(200, {"result": _eval_item(result), "artifact": artifact})


def _run_evals_job(job: dict[str, Any]) -> dict[str, Any]:
    """Background worker: evaluate a run and persist the aggregate."""
    user_id = str(job.get("userId") or "")
    run_id = str(job.get("runId") or "")
    try:
        return evals_runner.run_evaluation(user_id=user_id, run_id=run_id)
    except Exception as exc:  # noqa: BLE001 - never leave a stuck run
        print(f"eval run failed: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        try:
            evals_repo.update_run(
                user_id,
                run_id,
                status=evals_repo.RUN_FAILED,
                error=str(exc)[:500],
                completedAt=now_iso(),
            )
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": "evaluation failed"}


# --- evaluation lab: AWS-native curation --------------------------------------
#
# The curation surface (traces, datasets, queues, score configs, metrics) is
# served from the AWS-native Lab store (DynamoDB + CloudWatch).
# namespaced into every dataset/queue/score-config name (``u_<userId>/<name>``)
# so a user can only ever see or touch their own objects. Traces come from the
# caller's stored conversations; the only place a trace can be added to a
# dataset or an annotation queue is the traces page.

_LAB_NAMESPACE = "u_"
# Traces produced by the eval mirror itself are hidden from the traces page.
_LAB_HIDDEN_TRACE_PREFIXES = ("eval",)


def _lab_configured() -> bool:
    return lab_store.configured()


def _lab_prefix(sub: str) -> str:
    return f"{_LAB_NAMESPACE}{sub}/"


def _lab_name(sub: str, name: str) -> str:
    return f"{_lab_prefix(sub)}{name}"


def _lab_display_name(sub: str, name: str) -> str:
    prefix = _lab_prefix(sub)
    return name[len(prefix) :] if name.startswith(prefix) else name


def _lab_request(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    """Serve the /v1/lab routes from the AWS-native Lab store (DynamoDB)."""
    try:
        return lab_store.lab_request(method, path, payload)
    except lab_store.StoreError as exc:
        raise ApiError(404, str(exc)[:300]) from exc


def _lab_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _lab_require_name(body: dict[str, Any]) -> str:
    name = str(body.get("name") or "").strip()
    if not name:
        raise ApiError(400, "Name is required")
    if len(name) > 120:
        raise ApiError(400, "Name is too long")
    return name


def _lab_trace_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or item.get("traceId"),
        "traceId": item.get("traceId") or item.get("id"),
        "name": str(item.get("name") or ""),
        "userId": item.get("userId"),
        "timestamp": item.get("timestamp"),
        "sessionId": item.get("sessionId"),
        "conversationId": item.get("conversationId"),
        "agentId": item.get("agentId"),
        "agentName": item.get("agentName"),
        "model": item.get("model"),
        "status": item.get("status") or "ok",
        "level": item.get("level") or "DEFAULT",
        "latency": item.get("latency"),
        "latencyMs": item.get("latencyMs"),
        "tags": item.get("tags") or [],
        "input": item.get("input"),
        "output": item.get("output"),
        "usage": item.get("usage") or {},
        "costMicroUsd": item.get("costMicroUsd") or 0,
        "observationCount": item.get("observationCount") or 0,
    }


def _lab_summaries(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _lab_trace_summary(item)
        for item in items
        if not str(item.get("name") or "").startswith(_LAB_HIDDEN_TRACE_PREFIXES)
    ]


def _lab_owned(item: dict[str, Any], ids: set[str]) -> bool:
    """True when a trace belongs to one of the caller's identifiers."""
    if str(item.get("userId") or "") in ids:
        return True
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        for key in ("userId", "user_id", "user"):
            if str(metadata.get(key) or "") in ids:
                return True
    return False


def _handle_lab_traces(claims: dict[str, Any], query: dict[str, str]) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    if not _lab_configured():
        return _json(200, {"configured": False, "traces": []})
    limit = _lab_int(query.get("limit"), 25, 1, 100)
    cursor = str(query.get("cursor") or "").strip() or None
    agent_id = str(query.get("agentId") or "").strip() or None
    path = f"/v2/traces?userId={quote(sub)}&limit={limit}"
    if cursor:
        path += f"&cursor={quote(cursor, safe='')}"
    if agent_id:
        path += f"&agentId={quote(agent_id)}"
    try:
        payload = _lab_request("GET", path)
    except ApiError as exc:
        return _json(
            200,
            {"configured": True, "traces": [], "error": str(exc)[:300]},
        )
    traces = _lab_summaries(payload.get("data") or [])
    meta = payload.get("meta") or {}
    return _json(
        200,
        {
            "configured": True,
            "traces": traces,
            "nextCursor": meta.get("cursor"),
        },
    )


def _handle_lab_datasets_list(claims: dict[str, Any]) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    if not _lab_configured():
        return _json(200, {"configured": False, "datasets": []})
    payload = _lab_request("GET", "/datasets?limit=100")
    prefix = _lab_prefix(sub)
    datasets = [
        {
            "name": _lab_display_name(sub, str(item.get("name") or "")),
            "fullName": str(item.get("name") or ""),
            "description": str(item.get("description") or ""),
            "createdAt": item.get("createdAt"),
        }
        for item in (payload.get("data") or [])
        if str(item.get("name") or "").startswith(prefix)
    ]
    return _json(200, {"configured": True, "datasets": datasets})


def _handle_lab_dataset_create(
    claims: dict[str, Any], body: dict[str, Any]
) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    name = _lab_require_name(body)
    full = _lab_name(sub, name)
    _lab_request(
        "POST",
        "/datasets",
        {"name": full, "description": str(body.get("description") or "")[:1000]},
    )
    return _json(201, {"dataset": {"name": name, "fullName": full}})


def _lab_dataset_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", (value or "").strip().lower())
    return re.sub(r"-{2,}", "-", slug).strip("-")[:48].strip("-")


def _handle_lab_trace_dataset(
    claims: dict[str, Any], trace_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    raw = str(body.get("datasetName") or "").strip()
    if not raw:
        raise ApiError(400, "Select or name a dataset")
    if raw.startswith(_lab_prefix(sub)):
        full = raw
        name = _lab_display_name(sub, raw)
    else:
        name = _lab_dataset_slug(raw)
        if not name:
            raise ApiError(400, "Give the dataset a valid name")
        full = _lab_name(sub, name)

    # Create the dataset on demand: the traces page can start a new one inline.
    try:
        _lab_request("GET", f"/datasets/{quote(full, safe='')}")
    except ApiError:
        try:
            _lab_request("POST", "/datasets", {"name": full, "description": ""})
        except ApiError:
            pass  # created concurrently, or already exists

    expected = str(body.get("expectedOutput") or "")
    input_value = body.get("input")
    if not isinstance(input_value, (dict, list, str)):
        input_value = {"question": str(body.get("question") or "")}
    item_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"get1agent:dataset-item:{full}:{trace_id}")
    )
    payload: dict[str, Any] = {
        "id": item_id,
        "datasetName": full,
        "input": input_value,
        "sourceTraceId": trace_id,
    }
    if expected:
        payload["expectedOutput"] = expected
    _lab_request("POST", "/dataset-items", payload)
    return _json(201, {"ok": True, "itemId": item_id, "datasetName": name})


def _handle_lab_queues_list(claims: dict[str, Any]) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    if not _lab_configured():
        return _json(200, {"configured": False, "queues": []})
    payload = _lab_request("GET", "/annotation-queues?limit=100")
    prefix = _lab_prefix(sub)
    queues = [
        {
            "id": item.get("id"),
            "name": _lab_display_name(sub, str(item.get("name") or "")),
            "description": str(item.get("description") or ""),
            "scoreConfigIds": item.get("scoreConfigIds") or [],
        }
        for item in (payload.get("data") or [])
        if str(item.get("name") or "").startswith(prefix)
    ]
    return _json(200, {"configured": True, "queues": queues})


def _handle_lab_queue_create(
    claims: dict[str, Any], body: dict[str, Any]
) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    name = _lab_require_name(body)
    raw_configs = body.get("scoreConfigIds")
    score_config_ids = (
        [str(value) for value in raw_configs if value]
        if isinstance(raw_configs, list)
        else []
    )
    payload: dict[str, Any] = {
        "name": _lab_name(sub, name),
        "description": str(body.get("description") or "")[:1000],
    }
    if score_config_ids:
        payload["scoreConfigIds"] = score_config_ids
    created = _lab_request("POST", "/annotation-queues", payload)
    return _json(
        201,
        {
            "queue": {
                "id": (created or {}).get("id"),
                "name": name,
                "description": payload["description"],
                "scoreConfigIds": score_config_ids,
            }
        },
    )


def _handle_lab_trace_queue(
    claims: dict[str, Any], trace_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    queue_id = str(body.get("queueId") or "").strip()
    if not queue_id:
        raise ApiError(400, "Select a queue")
    # Ownership: the queue must be one of the caller's namespaced queues.
    _lab_owned_queue_id(claims, queue_id)
    _lab_request(
        "POST",
        f"/annotation-queues/{quote(queue_id)}/items",
        {"objectId": trace_id, "objectType": "TRACE"},
    )
    return _json(200, {"ok": True})


def _handle_lab_score_configs_list(claims: dict[str, Any]) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    if not _lab_configured():
        return _json(200, {"configured": False, "scoreConfigs": []})
    payload = _lab_request("GET", "/score-configs?limit=100")
    prefix = _lab_prefix(sub)
    configs = [
        {
            "id": item.get("id"),
            "name": _lab_display_name(sub, str(item.get("name") or "")),
            "dataType": item.get("dataType"),
            "categories": item.get("categories") or [],
            "minValue": item.get("minValue"),
            "maxValue": item.get("maxValue"),
        }
        for item in (payload.get("data") or [])
        if str(item.get("name") or "").startswith(prefix)
    ]
    return _json(200, {"configured": True, "scoreConfigs": configs})


def _handle_lab_score_config_create(
    claims: dict[str, Any], body: dict[str, Any]
) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    name = _lab_require_name(body)
    data_type = str(body.get("dataType") or "CATEGORICAL").upper()
    if data_type not in ("NUMERIC", "CATEGORICAL", "BOOLEAN", "TEXT"):
        raise ApiError(400, "dataType must be NUMERIC, CATEGORICAL, BOOLEAN or TEXT")
    payload: dict[str, Any] = {"name": _lab_name(sub, name), "dataType": data_type}
    if data_type == "NUMERIC":
        payload["minValue"] = float(body.get("minValue", 0))
        payload["maxValue"] = float(body.get("maxValue", 1))
    if data_type == "CATEGORICAL":
        raw = body.get("categories")
        categories = (
            [{"label": str(value)} for value in raw if str(value).strip()]
            if isinstance(raw, list)
            else []
        )
        if not categories:
            raise ApiError(400, "Categorical configs need at least one category")
        payload["categories"] = categories
    created = _lab_request("POST", "/score-configs", payload)
    return _json(
        201,
        {
            "scoreConfig": {
                "id": (created or {}).get("id"),
                "name": name,
                "dataType": data_type,
            }
        },
    )


def _lab_owned_queue_id(claims: dict[str, Any], queue_id: str) -> None:
    listing = json.loads(_handle_lab_queues_list(claims)["body"])
    if queue_id not in {queue.get("id") for queue in listing.get("queues") or []}:
        raise ApiError(404, "Queue not found")


def _handle_lab_trace_detail(claims: dict[str, Any], trace_id: str) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    try:
        trace = _lab_request(
            "GET", f"/traces/{quote(trace_id, safe='')}?userId={quote(sub, safe='')}"
        )
    except ApiError as exc:
        raise ApiError(404, f"Trace not found: {exc}") from exc
    return _json(200, {"trace": trace})


def _handle_lab_queue_items(claims: dict[str, Any], queue_id: str) -> dict[str, Any]:
    get_or_create_user(claims)
    _lab_owned_queue_id(claims, queue_id)
    payload = _lab_request(
        "GET",
        f"/annotation-queues/{quote(queue_id)}/items?status=PENDING&limit=100",
    )
    return _json(200, {"items": payload.get("data") or []})


def _handle_lab_queue_item_score(
    claims: dict[str, Any], queue_id: str, item_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    get_or_create_user(claims)
    _lab_owned_queue_id(claims, queue_id)
    item = _lab_request(
        "GET", f"/annotation-queues/{quote(queue_id)}/items/{quote(item_id)}"
    )
    trace_id = str((item or {}).get("objectId") or "")
    if not trace_id:
        raise ApiError(404, "Queue item has no trace")

    raw_scores = body.get("scores")
    if isinstance(raw_scores, list):
        for score in raw_scores:
            if not isinstance(score, dict):
                continue
            name = str(score.get("name") or "").strip()
            if not name:
                continue
            payload: dict[str, Any] = {"traceId": trace_id, "name": name}
            if score.get("comment"):
                payload["comment"] = str(score["comment"])[:2000]
            if score.get("configId"):
                payload["configId"] = str(score["configId"])
            if score.get("value") is not None and score.get("value") != "":
                try:
                    payload["value"] = float(score["value"])
                except (TypeError, ValueError):
                    pass
            if score.get("stringValue") not in (None, ""):
                payload["stringValue"] = str(score["stringValue"])[:500]
            _lab_request("POST", "/scores", payload)

    if body.get("complete"):
        _lab_request(
            "PATCH",
            f"/annotation-queues/{quote(queue_id)}/items/{quote(item_id)}",
            {"status": "COMPLETED"},
        )
    return _json(200, {"ok": True})


def _handle_lab_metrics(claims: dict[str, Any], query: dict[str, str]) -> dict[str, Any]:
    sub = get_or_create_user(claims)["userId"]
    if not _lab_configured():
        return _json(200, {"configured": False})
    days = _lab_int(query.get("days"), 7, 1, 90)
    root_filter = {
        "column": "isRootObservation",
        "operator": "=",
        "value": True,
        "type": "boolean",
    }

    def _num(value: Any) -> float:
        try:
            return round(float(value), 4)
        except (TypeError, ValueError):
            return 0.0

    def run(view, metrics, *, dimensions=None, time_dimension=None, order_by=None,
            filters=None, row_limit=100):
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)
        payload: dict[str, Any] = {
            "view": view,
            "metrics": metrics,
            "dimensions": dimensions or [],
            "filters": [
                {"column": "userId", "operator": "=", "value": sub, "type": "string"},
                *(filters or []),
            ],
            "fromTimestamp": start.isoformat(),
            "toTimestamp": now.isoformat(),
            "config": {"row_limit": row_limit},
        }
        if time_dimension:
            payload["timeDimension"] = {"granularity": time_dimension}
        if order_by:
            payload["orderBy"] = order_by
        path = "/v2/metrics?query=" + quote(json_dumps(payload), safe="")
        return _lab_request("GET", path)

    try:
        totals = run(
            "observations",
            [
                {"measure": "count", "aggregation": "count"},
                {"measure": "latency", "aggregation": "avg"},
                {"measure": "latency", "aggregation": "p95"},
                {"measure": "totalCost", "aggregation": "sum"},
            ],
            filters=[root_filter],
            row_limit=1,
        )
        series = run(
            "observations",
            [
                {"measure": "count", "aggregation": "count"},
                {"measure": "latency", "aggregation": "p95"},
                {"measure": "totalCost", "aggregation": "sum"},
            ],
            time_dimension="day",
            order_by=[{"field": "time_dimension", "direction": "asc"}],
            filters=[root_filter],
            row_limit=100,
        )
    except ApiError as exc:
        return _json(200, {"configured": True, "error": str(exc)[:300]})

    # Scores and tokens are best-effort (measure/field names vary by version).
    scores: list[dict[str, Any]] = []
    try:
        score_rows = run(
            "scores-numeric",
            [
                {"measure": "value", "aggregation": "avg"},
                {"measure": "count", "aggregation": "count"},
            ],
            dimensions=[{"field": "name"}],
            order_by=[{"field": "avg_value", "direction": "desc"}],
            row_limit=25,
        )
        scores = [
            {
                "name": str(row.get("name") or ""),
                "avg": _num(row.get("avg_value")),
                "count": _num(row.get("count_count")),
            }
            for row in (score_rows.get("data") or [])
            if row.get("name")
        ]
    except ApiError:
        scores = []

    tokens = None
    try:
        token_rows = run(
            "observations",
            [{"measure": "totalTokens", "aggregation": "sum"}],
            filters=[root_filter],
            row_limit=1,
        )
        tokens = _num((token_rows.get("data") or [{}])[0].get("sum_totalTokens"))
    except ApiError:
        tokens = None

    # Per-model breakdown (best-effort: the model dimension name varies by
    # version, so try the documented one then fall back).
    models: list[dict[str, Any]] = []
    for dimension in ("providedModelName", "model"):
        try:
            model_rows = run(
                "observations",
                [
                    {"measure": "count", "aggregation": "count"},
                    {"measure": "totalCost", "aggregation": "sum"},
                    {"measure": "totalTokens", "aggregation": "sum"},
                ],
                dimensions=[{"field": dimension}],
                order_by=[{"field": "sum_totalCost", "direction": "desc"}],
                filters=[root_filter],
                row_limit=12,
            )
        except ApiError:
            continue
        models = [
            {
                "model": str(row.get(dimension) or "unknown"),
                "count": _num(row.get("count_count")),
                "cost": _num(row.get("sum_totalCost")),
                "tokens": _num(row.get("sum_totalTokens")),
            }
            for row in (model_rows.get("data") or [])
            if row.get(dimension)
        ]
        break

    total_row = (totals.get("data") or [{}])[0]
    return _json(
        200,
        {
            "configured": True,
            "days": days,
            "totals": {
                "traces": _num(total_row.get("count_count")),
                "avgLatency": _num(total_row.get("avg_latency")),
                "p95Latency": _num(total_row.get("p95_latency")),
                "cost": _num(total_row.get("sum_totalCost")),
                "tokens": tokens,
            },
            "series": [
                {
                    "date": str(row.get("time_dimension") or ""),
                    "count": _num(row.get("count_count")),
                    "p95Latency": _num(row.get("p95_latency")),
                    "cost": _num(row.get("sum_totalCost")),
                }
                for row in (series.get("data") or [])
            ],
            "scores": scores,
            "models": models,
        },
    )


def _handle_lab_playground_run(
    claims: dict[str, Any], body: dict[str, Any]
) -> dict[str, Any]:
    sub = _require_budget(claims)

    raw_runs = body.get("runs")
    if isinstance(raw_runs, list) and raw_runs:
        specs = [entry for entry in raw_runs[:4] if isinstance(entry, dict)]
    else:
        specs = [
            {
                "model": body.get("model"),
                "messages": body.get("messages"),
                "temperature": body.get("temperature"),
                "maxTokens": body.get("maxTokens"),
            }
        ]
    if not specs:
        raise ApiError(400, "No runs provided")
    for spec in specs:
        if str(spec.get("model") or "").strip() not in evals_config.PLAYGROUND_MODELS:
            raise ApiError(400, "Unsupported model")

    def run_one(spec: dict[str, Any]) -> dict[str, Any]:
        model = str(spec.get("model") or "").strip()
        try:
            result = evals_playground.run_completion(
                model=model,
                messages=spec.get("messages"),
                temperature=spec.get("temperature"),
                max_tokens=spec.get("maxTokens"),
            )
            return {"ok": True, **result}
        except evals_playground.PlaygroundError as exc:
            return {"ok": False, "model": model, "error": str(exc)[:300]}

    if len(specs) == 1:
        results = [run_one(specs[0])]
    else:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=min(len(specs), 4)) as pool:
            results = list(pool.map(run_one, specs))

    # Charge each replay to the user's application budget.
    for result in results:
        if not result.get("ok"):
            continue
        usage = result.get("usage") or {}
        try:
            charge_usage(
                sub,
                model=str(result.get("model") or ""),
                input_tokens=usage.get("input") or 0,
                output_tokens=usage.get("output") or 0,
            )
        except Exception:  # noqa: BLE001 - accounting never fails the replay
            pass
    return _json(200, {"results": results})


def _handle_lab_playground_judge(
    claims: dict[str, Any], body: dict[str, Any]
) -> dict[str, Any]:
    _require_budget(claims)
    if not evals_config.enabled():
        raise ApiError(400, "The evaluation model gateway is not configured")
    query = str(body.get("query") or "").strip()
    answer = str(body.get("answer") or "").strip()
    if not query or not answer:
        raise ApiError(400, "query and answer are required")
    expected = str(body.get("expectedOutput") or "").strip()

    contexts: list[dict[str, Any]] = []
    raw_contexts = body.get("contexts")
    if isinstance(raw_contexts, list):
        for entry in raw_contexts[:20]:
            text = entry if isinstance(entry, str) else (
                entry.get("text") if isinstance(entry, dict) else ""
            )
            text = str(text or "").strip()
            if text:
                contexts.append({"text": text[:4000]})

    try:
        relevance = evals_judge.judge_relevance(query, answer)
        metrics: dict[str, Any] = {
            "answer_relevance": {
                "value": relevance["answer_relevance"],
                "reasoning": relevance["reasoning"],
            }
        }
        if expected:
            correctness = evals_judge.judge_correctness(query, answer, expected)
            metrics["answer_correctness"] = {
                "value": correctness["answer_correctness"],
                "reasoning": correctness["reasoning"],
            }
        if contexts:
            faithfulness = evals_judge.judge_faithfulness(query, answer, contexts)
            metrics["faithfulness"] = {
                "value": faithfulness["faithfulness"],
                "claims": faithfulness["claims"],
                "reasoning": faithfulness["reasoning"],
            }
            context_relevance = evals_judge.judge_context_relevance(query, contexts)
            metrics["context_relevance"] = {
                "value": context_relevance["context_relevance"],
                "reasoning": context_relevance["reasoning"],
            }
    except evals_judge.JudgeError as exc:
        raise ApiError(502, str(exc)[:300]) from exc
    return _json(200, {"metrics": metrics})


def _route_identity(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
    query: dict[str, str],
):
    """AgentCore Identity: provider status + on-demand OAuth tokens."""
    if not rest:
        if method == "GET":
            return _handle_identity_status(claims)
        raise ApiError(405, f"Method not allowed: {method}")
    if rest[0] == "token" and method == "POST":
        return _handle_identity_token(claims, body)
    if rest[0] == "callback" and method == "GET":
        # Public redirect target registered as the provider return URL.
        return _json(200, {"ok": True, "state": query.get("state")})
    raise ApiError(404, "Not found")


def _handle_identity_status(claims: dict[str, Any]) -> dict[str, Any]:
    from core import identity

    get_or_create_user(claims)
    return _json(200, identity.describe())


def _handle_identity_token(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Fetch a user's third-party OAuth token from the managed token vault.

    Only the provider key is accepted from the client — never a client secret.
    """
    from core import identity

    profile = get_or_create_user(claims)
    provider = str(body.get("provider") or "").strip()
    if not provider:
        raise ApiError(400, "provider is required")
    scopes = body.get("scopes")
    scope_list = (
        [str(value) for value in scopes if str(value).strip()]
        if isinstance(scopes, list)
        else []
    )
    if not identity.enabled():
        raise ApiError(400, "AgentCore Identity is not configured for this workspace")
    try:
        token = identity.get_token(
            profile["userId"], provider, scopes=scope_list or None
        )
    except RuntimeError as exc:
        raise ApiError(400, str(exc)[:300]) from exc
    except Exception as exc:  # noqa: BLE001 - provider/authorization failure
        raise ApiError(502, f"Identity token request failed: {exc}") from exc

    # Never echo a live token to the client; only its shape/lifetime.
    return _json(
        200,
        {
            "provider": provider,
            "obtained": bool(token.get("accessToken")),
            "expiresAt": token.get("expiresAt"),
            "scopes": token.get("scopes") or scope_list,
        },
    )


def _route_browser(
    claims: dict[str, Any], method: str, rest: list[str], body: dict[str, Any]
):
    """AgentCore Browser: status, allowlist check, session lifecycle."""
    from core import browser

    get_or_create_user(claims)

    if not rest:
        if method == "GET":
            return _json(200, browser.describe())
        raise ApiError(405, f"Method not allowed: {method}")

    if rest[0] == "check" and method == "POST":
        url = str(body.get("url") or "").strip()
        if not url:
            raise ApiError(400, "url is required")
        allowed, reason = browser.allowed(url)
        return _json(200, {"allowed": allowed, "reason": reason})

    # Order matters: the exact `session/close` route must be matched before the
    # generic `session` route, which would otherwise swallow it.
    if rest == ["session", "close"] and method == "POST":
        session_id = str(body.get("sessionId") or "").strip()
        if not session_id:
            raise ApiError(400, "sessionId is required")
        return _json(200, {"stopped": browser.stop_session(session_id)})

    if rest == ["session"] and method == "POST":
        url = str(body.get("url") or "").strip()
        if not url:
            raise ApiError(400, "url is required")
        if not browser.enabled():
            raise ApiError(400, "AgentCore Browser is not configured")
        allowed, reason = browser.allowed(url)
        if not allowed:
            raise ApiError(403, reason)
        try:
            return _json(200, browser.start_session())
        except Exception as exc:  # noqa: BLE001
            raise ApiError(502, f"Browser session failed: {exc}") from exc

    if rest == ["session"] and method == "DELETE":
        session_id = str(body.get("sessionId") or "").strip()
        if not session_id:
            raise ApiError(400, "sessionId is required")
        return _json(200, {"stopped": browser.stop_session(session_id)})

    raise ApiError(404, "Not found")


def _route_guardrails(
    claims: dict[str, Any], method: str, rest: list[str], body: dict[str, Any]
):
    """Bedrock Guardrails: the user's guardrails, the workspace default, a tester."""
    if not rest:
        if method == "GET":
            return _handle_guardrails_list(claims)
        if method == "POST":
            return _handle_guardrail_create(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")
    segment = rest[0]
    if segment == "test" and method == "POST":
        return _handle_guardrail_test(claims, body)
    if segment == "config" and method == "PUT":
        return _handle_guardrail_config(claims, body)
    if segment in _GUARDRAIL_RESERVED:
        raise ApiError(404, "Not found")
    name = _validated_guardrail_name(segment)
    if method == "GET":
        return _handle_guardrail_detail(claims, name)
    if method == "PUT":
        return _handle_guardrail_update(claims, name, body)
    if method == "DELETE":
        return _handle_guardrail_delete(claims, name)
    raise ApiError(405, f"Method not allowed: {method}")


def _handle_guardrails_list(claims: dict[str, Any]) -> dict[str, Any]:
    from core import guardrails

    profile = get_or_create_user(claims)
    sub = profile["userId"]
    items = guardrails_repo.list_guardrails(sub)
    settings = settings_repo.get_settings(sub) or {}
    workspace_id = str(settings.get("guardrailId") or "").strip()
    workspace_version = str(settings.get("guardrailVersion") or "").strip()
    # The effective default: the user's workspace guardrail, else the
    # platform-wide one (if any).
    effective_id = workspace_id or guardrails.guardrail_id()
    effective_version = (
        workspace_version if workspace_id else guardrails.guardrail_version() if effective_id else ""
    )
    return _json(
        200,
        {
            "guardrails": [_serialize_guardrail(item) for item in items],
            "defaultGuardrailId": workspace_id,
            "platformGuardrailId": guardrails.guardrail_id(),
            "configured": bool(effective_id),
            "guardrailId": effective_id or None,
            "version": effective_version or None,
            "region": guardrails.region(),
            "limit": MAX_GUARDRAILS_PER_USER,
        },
    )


def _handle_guardrail_create(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    from core import guardrails

    profile = get_or_create_user(claims)
    sub = profile["userId"]
    if guardrails_repo.count_guardrails(sub) >= MAX_GUARDRAILS_PER_USER:
        raise ApiError(409, f"You can create at most {MAX_GUARDRAILS_PER_USER} guardrails")
    name = _validated_guardrail_name(body.get("name"))
    description = _bounded_text(
        body.get("description"), "description", MAX_GUARDRAIL_DESCRIPTION_LENGTH
    )
    config = _validated_guardrail_config(body.get("config"))
    blocked_input = _bounded_text(body.get("blockedInput"), "blockedInput", 500)
    blocked_output = _bounded_text(body.get("blockedOutput"), "blockedOutput", 500)
    try:
        created = guardrails.create_managed_guardrail(
            name=name,
            description=description,
            config=config,
            blocked_input=blocked_input,
            blocked_output=blocked_output,
        )
    except Exception as exc:  # noqa: BLE001 - surface a clean error
        raise ApiError(502, f"Could not create the guardrail: {exc}") from exc
    item = guardrails_repo.guardrail_item(
        user_id=sub,
        name=name,
        description=description,
        guardrail_id=created["guardrailId"],
        guardrail_arn=created["guardrailArn"],
        version=created["version"],
        status=created["status"],
        config=config,
        blocked_input=blocked_input or guardrails.DEFAULT_BLOCKED_INPUT,
        blocked_output=blocked_output or guardrails.DEFAULT_BLOCKED_OUTPUT,
    )
    try:
        guardrails_repo.create_guardrail(item)
    except DuplicateGuardrail as exc:
        # Roll back the Bedrock guardrail so a name clash leaves no orphan.
        try:
            guardrails.delete_managed_guardrail(created["guardrailId"])
        except Exception:  # noqa: BLE001 - best-effort cleanup
            pass
        raise ApiError(409, f'A guardrail named "{name}" already exists') from exc
    return _json(201, _serialize_guardrail(item))


def _handle_guardrail_detail(claims: dict[str, Any], name: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    item = guardrails_repo.get_guardrail(profile["userId"], name)
    if item is None:
        raise ApiError(404, "Guardrail not found")
    return _json(200, _serialize_guardrail(item))


def _handle_guardrail_update(
    claims: dict[str, Any], name: str, body: dict[str, Any]
) -> dict[str, Any]:
    from core import guardrails

    profile = get_or_create_user(claims)
    sub = profile["userId"]
    existing = guardrails_repo.get_guardrail(sub, name)
    if existing is None:
        raise ApiError(404, "Guardrail not found")
    description = _bounded_text(
        body.get("description"), "description", MAX_GUARDRAIL_DESCRIPTION_LENGTH
    )
    config = _validated_guardrail_config(body.get("config"))
    blocked_input = _bounded_text(body.get("blockedInput"), "blockedInput", 500)
    blocked_output = _bounded_text(body.get("blockedOutput"), "blockedOutput", 500)
    try:
        updated = guardrails.update_managed_guardrail(
            str(existing.get("guardrailId") or ""),
            name=name,
            description=description,
            config=config,
            blocked_input=blocked_input,
            blocked_output=blocked_output,
        )
    except Exception as exc:  # noqa: BLE001
        raise ApiError(502, f"Could not update the guardrail: {exc}") from exc
    item = guardrails_repo.update_guardrail(
        sub,
        name,
        description=description,
        guardrail_id=updated["guardrailId"] or str(existing.get("guardrailId") or ""),
        guardrail_arn=updated["guardrailArn"] or str(existing.get("guardrailArn") or ""),
        version=updated["version"],
        status=updated["status"],
        config=config,
        blocked_input=blocked_input or guardrails.DEFAULT_BLOCKED_INPUT,
        blocked_output=blocked_output or guardrails.DEFAULT_BLOCKED_OUTPUT,
    )
    if item is None:
        raise ApiError(404, "Guardrail not found")
    return _json(200, _serialize_guardrail(item))


def _handle_guardrail_delete(claims: dict[str, Any], name: str) -> dict[str, Any]:
    from core import guardrails

    profile = get_or_create_user(claims)
    sub = profile["userId"]
    existing = guardrails_repo.get_guardrail(sub, name)
    if existing is None:
        raise ApiError(404, "Guardrail not found")
    try:
        guardrails.delete_managed_guardrail(str(existing.get("guardrailId") or ""))
    except Exception as exc:  # noqa: BLE001
        raise ApiError(502, f"Could not delete the guardrail: {exc}") from exc
    guardrails_repo.delete_guardrail(sub, name)
    # Clear the workspace default if it pointed at the guardrail we removed.
    settings = settings_repo.get_settings(sub) or {}
    if str(settings.get("guardrailId") or "").strip() == str(
        existing.get("guardrailId") or ""
    ).strip():
        settings_repo.update_settings(
            sub,
            guardrail_id="",
            guardrail_version=guardrails.DEFAULT_GUARDRAIL_VERSION,
        )
    return _json(200, {"ok": True})



def _handle_guardrail_config(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Record the workspace's default guardrail.

    Stored on the user's settings item. An agent or workflow may use its own id;
    otherwise this default applies to its runs. The version is always Bedrock's
    ``DRAFT`` — it is intentionally not user-configurable.
    """
    from core import guardrails

    profile = get_or_create_user(claims)
    guardrail_id = str(body.get("guardrailId") or "").strip()
    if guardrail_id and not re.match(r"^[A-Za-z0-9_-]{1,64}$", guardrail_id):
        raise ApiError(400, "guardrailId must be alphanumeric (with - or _)")
    version = guardrails.DEFAULT_GUARDRAIL_VERSION
    settings_repo.update_settings(
        profile["userId"], guardrail_id=guardrail_id, guardrail_version=version
    )
    return _json(
        200,
        {"configured": bool(guardrail_id), "guardrailId": guardrail_id or None, "version": version},
    )


def _handle_guardrail_test(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    from core import guardrails

    profile = get_or_create_user(claims)
    text = str(body.get("text") or "").strip()
    if not text:
        raise ApiError(400, "text is required")
    if len(text) > 8000:
        raise ApiError(400, "text is too long")
    source = str(body.get("source") or "OUTPUT").strip().upper()
    if source not in ("INPUT", "OUTPUT"):
        raise ApiError(400, "source must be INPUT or OUTPUT")

    # The caller may test the id currently in the input field, else the saved
    # workspace default, else the platform guardrail.
    guardrail_id = str(body.get("guardrailId") or "").strip()
    version = str(body.get("version") or "").strip() or None
    if not guardrail_id:
        settings = settings_repo.get_settings(profile["userId"]) or {}
        guardrail_id = str(settings.get("guardrailId") or "").strip()
        version = version or str(settings.get("guardrailVersion") or "").strip() or None
    if not guardrail_id:
        guardrail_id = guardrails.guardrail_id()
        version = version or (guardrails.guardrail_version() if guardrail_id else None)
    if not guardrail_id:
        raise ApiError(400, "No Bedrock guardrail is configured for this workspace")
    try:
        result = guardrails.apply(
            text,
            source=source,
            guardrail_identifier=guardrail_id,
            guardrail_version=version,
        )
    except Exception as exc:  # noqa: BLE001 - surface a clean error
        raise ApiError(502, f"Guardrail check failed: {exc}") from exc
    return _json(200, {"result": result})


def _route_lab(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
    query: dict[str, str],
):
    if not rest:
        raise ApiError(404, "Not found")

    if rest[0] == "traces":
        if len(rest) == 1:
            if method == "GET":
                return _handle_lab_traces(claims, query)
            raise ApiError(405, f"Method not allowed: {method}")
        if len(rest) == 2 and method == "GET":
            return _handle_lab_trace_detail(claims, str(rest[1]).strip())
        if len(rest) == 3 and method == "POST":
            trace_id = str(rest[1]).strip()
            if not trace_id:
                raise ApiError(400, "Trace id is required")
            if rest[2] == "dataset":
                return _handle_lab_trace_dataset(claims, trace_id, body)
            if rest[2] == "queue":
                return _handle_lab_trace_queue(claims, trace_id, body)
        raise ApiError(404, "Not found")

    if rest[0] == "datasets":
        if len(rest) == 1:
            if method == "GET":
                return _handle_lab_datasets_list(claims)
            if method == "POST":
                return _handle_lab_dataset_create(claims, body)
            raise ApiError(405, f"Method not allowed: {method}")
        raise ApiError(404, "Not found")

    if rest[0] == "queues":
        if len(rest) == 1:
            if method == "GET":
                return _handle_lab_queues_list(claims)
            if method == "POST":
                return _handle_lab_queue_create(claims, body)
            raise ApiError(405, f"Method not allowed: {method}")
        if len(rest) == 3 and rest[2] == "items" and method == "GET":
            return _handle_lab_queue_items(claims, str(rest[1]).strip())
        if (
            len(rest) == 4
            and rest[2] == "items"
            and method == "POST"
        ):
            return _handle_lab_queue_item_score(
                claims, str(rest[1]).strip(), str(rest[3]).strip(), body
            )
        raise ApiError(404, "Not found")

    if rest[0] == "score-configs":
        if len(rest) == 1:
            if method == "GET":
                return _handle_lab_score_configs_list(claims)
            if method == "POST":
                return _handle_lab_score_config_create(claims, body)
            raise ApiError(405, f"Method not allowed: {method}")
        raise ApiError(404, "Not found")

    if rest[0] == "metrics":
        if len(rest) == 1 and method == "GET":
            return _handle_lab_metrics(claims, query)
        raise ApiError(404, "Not found")

    if rest[0] == "playground":
        if len(rest) == 2 and method == "POST":
            if rest[1] == "run":
                return _handle_lab_playground_run(claims, body)
            if rest[1] == "judge":
                return _handle_lab_playground_judge(claims, body)
        raise ApiError(404, "Not found")

    raise ApiError(404, "Not found")


# --- support & security -------------------------------------------------------


def _serialize_ticket(
    ticket: dict[str, Any], *, include_user: bool = False
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": ticket.get("ticketId"),
        "subject": ticket.get("subject") or "",
        "status": ticket.get("status") or support_repo.TICKET_OPEN,
        "createdAt": ticket.get("createdAt"),
        "updatedAt": ticket.get("updatedAt"),
        "messageCount": int(ticket.get("messageCount") or 0),
        "lastAuthor": ticket.get("lastAuthor") or support_repo.AUTHOR_USER,
        "lastMessage": ticket.get("lastMessage") or "",
    }
    if include_user:
        payload["userId"] = ticket.get("userId")
        payload["userEmail"] = ticket.get("userEmail") or ""
    return payload


def _serialize_message(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": message.get("messageId"),
        "author": message.get("author") or support_repo.AUTHOR_USER,
        "authorName": message.get("authorName") or "",
        "body": message.get("body") or "",
        "createdAt": message.get("createdAt"),
    }


def _serialize_security_report(
    report: dict[str, Any], *, include_user: bool = False
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": report.get("reportId"),
        "url": report.get("url") or "",
        "page": report.get("page") or "",
        "body": report.get("body") or "",
        "status": report.get("status") or support_repo.REPORT_NEW,
        "createdAt": report.get("createdAt"),
    }
    if include_user:
        payload["userId"] = report.get("userId")
        payload["userEmail"] = report.get("userEmail") or ""
    return payload


def _required_text(value: Any, label: str, max_length: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ApiError(400, f"{label} is required")
    if len(text) > max_length:
        raise ApiError(400, f"{label} must be {max_length} characters or fewer")
    return text


def _optional_text(value: Any, label: str, max_length: int) -> str:
    text = str(value or "").strip()
    if len(text) > max_length:
        raise ApiError(400, f"{label} must be {max_length} characters or fewer")
    return text


def _parse_ref(value: str, label: str) -> str:
    """Ticket/report ids are opaque 16-char hex refs, not UUIDs."""
    normalized = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", normalized):
        raise ApiError(404, f"{label} not found")
    return normalized


def _handle_support_list(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    tickets = support_repo.list_tickets(str(profile["userId"]))
    return _json(200, {"tickets": [_serialize_ticket(ticket) for ticket in tickets]})


def _handle_support_create(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    subject = _required_text(body.get("subject"), "Subject", support_repo.MAX_SUBJECT)
    message = _required_text(body.get("body"), "Message", support_repo.MAX_BODY)
    ticket = support_repo.create_ticket(
        str(profile["userId"]),
        user_email=str(profile.get("email") or ""),
        subject=subject,
        body=message,
    )
    return _json(201, {"ticket": _serialize_ticket(ticket)})


def _handle_support_detail(claims: dict[str, Any], ticket_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    ticket = support_repo.get_ticket(str(profile["userId"]), ticket_id)
    if not ticket:
        raise ApiError(404, "Ticket not found")
    messages = support_repo.list_messages(ticket_id)
    return _json(
        200,
        {
            "ticket": _serialize_ticket(ticket),
            "messages": [_serialize_message(message) for message in messages],
        },
    )


def _handle_support_reply(
    claims: dict[str, Any], ticket_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    ticket = support_repo.get_ticket(str(profile["userId"]), ticket_id)
    if not ticket:
        raise ApiError(404, "Ticket not found")
    if ticket.get("status") == support_repo.TICKET_CLOSED:
        raise ApiError(409, "This ticket is closed. Open a new message instead.")
    message = _required_text(body.get("body"), "Message", support_repo.MAX_BODY)
    created = support_repo.add_message(
        str(profile["userId"]),
        ticket_id,
        author=support_repo.AUTHOR_USER,
        author_name=str(profile.get("email") or "User"),
        body=message,
    )
    return _json(201, {"message": _serialize_message(created)})


def _handle_security_list(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    reports = support_repo.list_security_reports(str(profile["userId"]))
    return _json(
        200, {"reports": [_serialize_security_report(report) for report in reports]}
    )


def _handle_security_create(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    url = _optional_text(body.get("url"), "URL", support_repo.MAX_URL)
    page = _optional_text(body.get("page"), "Page", support_repo.MAX_PAGE)
    description = _required_text(body.get("body"), "Description", support_repo.MAX_BODY)
    report = support_repo.create_security_report(
        str(profile["userId"]),
        user_email=str(profile.get("email") or ""),
        url=url,
        page=page,
        body=description,
    )
    return _json(201, {"report": _serialize_security_report(report)})


def _route_support(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
):
    if rest == ["messages"]:
        if method == "GET":
            return _handle_support_list(claims)
        if method == "POST":
            return _handle_support_create(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")
    if len(rest) == 2 and rest[0] == "messages":
        if method == "GET":
            return _handle_support_detail(claims, _parse_ref(rest[1], "Ticket"))
        raise ApiError(405, f"Method not allowed: {method}")
    if len(rest) == 3 and rest[0] == "messages" and rest[2] == "reply":
        if method == "POST":
            return _handle_support_reply(claims, _parse_ref(rest[1], "Ticket"), body)
        raise ApiError(405, f"Method not allowed: {method}")
    raise ApiError(404, "Not found")


def _route_security(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
):
    if rest == ["reports"]:
        if method == "GET":
            return _handle_security_list(claims)
        if method == "POST":
            return _handle_security_create(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")
    raise ApiError(404, "Not found")


def _serialize_notification(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("notificationId") or ""),
        "kind": str(item.get("kind") or "info"),
        "title": str(item.get("title") or ""),
        "detail": str(item.get("detail") or ""),
        "link": item.get("link") or None,
        "read": bool(item.get("read")),
        "createdAt": item.get("createdAt"),
    }


def _handle_notifications_list(claims: dict[str, Any], query: dict[str, str]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    try:
        limit = int(query.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, notifications_repo.MAX_LIST))
    items = notifications_repo.list_notifications(sub, limit=limit)
    return _json(
        200,
        {
            "notifications": [_serialize_notification(item) for item in items],
            "unreadCount": notifications_repo.unread_count(sub),
        },
    )


def _handle_notification_mark_read(claims: dict[str, Any], notification_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    item = notifications_repo.mark_read(sub, notification_id)
    if item is None:
        raise ApiError(404, "Notification not found")
    return _json(200, {"ok": True, "notification": _serialize_notification(item)})


def _handle_notifications_mark_all_read(claims: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    updated = notifications_repo.mark_all_read(sub)
    return _json(200, {"ok": True, "updated": updated})


def _handle_notification_delete(claims: dict[str, Any], notification_id: str) -> dict[str, Any]:
    profile = get_or_create_user(claims)
    sub = profile["userId"]
    item = notifications_repo.delete_notification(sub, notification_id)
    if item is None:
        raise ApiError(404, "Notification not found")
    return _json(200, {"ok": True})


def _route_notifications(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    query: dict[str, str],
):
    if not rest:
        if method == "GET":
            return _handle_notifications_list(claims, query)
        raise ApiError(405, f"Method not allowed: {method}")

    # Static action segments must be matched before notification ids.
    if rest == ["read-all"]:
        if method == "POST":
            return _handle_notifications_mark_all_read(claims)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 2 and rest[1] == "read":
        if method == "POST":
            return _handle_notification_mark_read(claims, _parse_id(rest[0], "Notification"))
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 1:
        if method == "DELETE":
            return _handle_notification_delete(claims, _parse_id(rest[0], "Notification"))
        raise ApiError(405, f"Method not allowed: {method}")

    raise ApiError(404, "Not found")


def _route(
    claims: dict[str, Any],
    method: str,
    segments: list[str],
    body: dict[str, Any],
    query: dict[str, str],
):
    if segments[:2] == ["v1", "support"]:
        return _route_support(claims, method, segments[2:], body)
    if segments[:2] == ["v1", "security"]:
        return _route_security(claims, method, segments[2:], body)
    if segments[:2] == ["v1", "knowledge-bases"]:
        return _route_knowledge_bases(claims, method, segments[2:], body, query)
    if segments[:2] == ["v1", "agent-skills"]:
        return _route_agent_skills(claims, method, segments[2:], body, query)
    if segments[:2] == ["v1", "custom-tools"]:
        return _route_custom_tools(claims, method, segments[2:], body, query)
    if segments[:2] == ["v1", "agents"]:
        return _route_agents(claims, method, segments[2:], body, query)
    if segments[:2] == ["v1", "workflows"]:
        return _route_workflows(claims, method, segments[2:], body, query)
    if segments[:2] == ["v1", "conversations"]:
        return _route_conversations(claims, method, segments[2:], body, query)
    if segments[:2] == ["v1", "evals"]:
        return _route_evals(claims, method, segments[2:], body, query)
    if segments[:2] == ["v1", "guardrails"]:
        return _route_guardrails(claims, method, segments[2:], body)
    if segments[:2] == ["v1", "identity"]:
        return _route_identity(claims, method, segments[2:], body, query)
    if segments[:2] == ["v1", "browser"]:
        return _route_browser(claims, method, segments[2:], body)
    if segments[:2] == ["v1", "lab"]:
        return _route_lab(claims, method, segments[2:], body, query)
    if segments[:2] == ["v1", "feedback"]:
        if method == "PUT" and len(segments) == 3:
            return _handle_feedback_put(claims, segments[2], body)
        raise ApiError(405, f"Method not allowed: {method}")
    if segments[:2] == ["v1", "vault"]:
        return _route_vault(claims, method, segments[2:], body)
    if segments[:2] == ["v1", "storage"]:
        return _route_storage(claims, method, segments[2:], body)
    if segments[:2] == ["v1", "notifications"]:
        return _route_notifications(claims, method, segments[2:], query)
    if segments[:2] == ["v1", "user"]:
        return _route_user(claims, method, segments[2:], body)
    raise ApiError(404, "Not found")


def _route_user(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
):
    """Account, consent, data-rights and grievance routes (DPDP)."""
    if rest == ["settings"]:
        if method == "GET":
            return _handle_settings_get(claims)
        if method == "POST":
            return _handle_settings_post(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")
    if rest == ["consent"]:
        if method == "GET":
            return _handle_consent_get(claims)
        if method == "POST":
            return _handle_consent_post(claims, body)
        if method == "DELETE":
            return _handle_consent_withdraw(claims)
        raise ApiError(405, f"Method not allowed: {method}")
    if rest == ["export"]:
        if method == "GET":
            return _handle_user_export(claims)
        raise ApiError(405, f"Method not allowed: {method}")
    if rest == ["account"]:
        if method == "DELETE":
            return _handle_user_account_delete(claims)
        raise ApiError(405, f"Method not allowed: {method}")
    if rest == ["grievances"]:
        if method == "GET":
            return _handle_grievance_list(claims)
        if method == "POST":
            return _handle_grievance_create(claims, body)
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


def _route_custom_tools(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
    query: dict[str, str],
):
    if not rest:
        if method == "GET":
            return _handle_custom_tools_list(claims)
        if method == "POST":
            return _handle_custom_tools_create(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    # Static action segments must be matched before ids.
    if len(rest) == 1 and rest[0] == "generate":
        if method == "POST":
            return _handle_custom_tools_generate(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 1 and rest[0] == "test":
        if method == "POST":
            return _handle_custom_tools_test(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    # The Playground's build-chat sessions live under their own static prefix.
    if rest[0] == "sessions":
        return _route_playground_sessions(claims, method, rest[1:], body, query)

    server_id = _parse_id(rest[0], "Custom tool server")

    if len(rest) == 1:
        if method == "GET":
            return _handle_custom_tools_detail(claims, server_id)
        if method == "PUT":
            return _handle_custom_tools_update(claims, server_id, body)
        if method == "DELETE":
            return _handle_custom_tools_delete(claims, server_id)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 2 and rest[1] == "tools":
        if method == "POST":
            return _handle_custom_tool_create(claims, server_id, body)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 3 and rest[1] == "tools":
        tool_id = _parse_id(rest[2], "Custom tool")
        if method == "GET":
            return _handle_custom_tool_detail(claims, server_id, tool_id)
        if method == "PUT":
            return _handle_custom_tool_update(claims, server_id, tool_id, body)
        if method == "DELETE":
            return _handle_custom_tool_delete(claims, server_id, tool_id)
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


def _route_workflows(
    claims: dict[str, Any],
    method: str,
    rest: list[str],
    body: dict[str, Any],
    query: dict[str, str],
):
    if not rest:
        if method == "GET":
            return _handle_workflow_list(claims)
        if method == "POST":
            return _handle_workflow_create(claims, body)
        raise ApiError(405, f"Method not allowed: {method}")

    workflow_id = _parse_id(rest[0], "Workflow")

    if len(rest) == 1:
        if method == "GET":
            return _handle_workflow_detail(claims, workflow_id)
        if method == "PUT":
            return _handle_workflow_update(claims, workflow_id, body)
        if method == "DELETE":
            return _handle_workflow_delete(claims, workflow_id)
        raise ApiError(405, f"Method not allowed: {method}")

    if len(rest) == 2:
        action = rest[1]
        if method == "GET" and action == "runs":
            return _handle_workflow_runs(claims, workflow_id, query)
        if method == "POST" and action == "verify":
            return _handle_workflow_verify(claims, workflow_id)
        raise ApiError(405, f"Method not allowed: {method}")

    raise ApiError(404, "Not found")


def lambda_handler(event: dict[str, Any], _context) -> dict[str, Any]:
    # Background invocations carry a private action marker instead of an API
    # Gateway event; they never reached the gateway and need no auth.
    if isinstance(event, dict) and _ASYNC_ACTION in event:
        return _run_async_job(event)

    method = _method(event)
    segments = _segments(event)
    # Public (unauthenticated): signed, expiring trace links.
    if method == "GET" and len(segments) == 3 and segments[0] == "v1" and segments[1] == "traces":
        return _handle_trace(segments[2])

    claims = _claims(event)
    if not claims:
        return _json(401, {"error": "Unauthorized"})
    # Strict separation: admins must be in the user view to use this API.
    try:
        require_user(claims, event)
    except AuthError as exc:
        return _json(exc.status, {"error": exc.message})

    try:
        return _route(claims, method, segments, _body(event), _query(event))
    except ApiError as exc:
        return _json(exc.status, {"error": exc.message})
    except ValueError as exc:
        return _json(400, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        print(f"user-api error: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        return _json(500, {"error": "Internal server error"})
