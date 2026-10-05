"""storage service logic (no MCP/AWS-transport dependencies).

The server owns the caller's standalone storage area and exposes four tools:

* ``list-storage-files`` — list the caller's stored files.
* ``read-storage-file`` — read one stored file back as text, parsed JSON or
  base64.
* ``write-storage-file`` — write a new file (text or base64) and return its
  metadata plus a presigned download URL.
* ``delete-storage-file`` — delete a stored file and its metadata.

Files are first-class user storage: they live under ``storage/<userId>/…`` and
carry a ``STORAGE#<fileId>`` item, so they appear on the Storage page and obey
the same limits as uploaded files (10 files, 30 MB each, 100 MB total).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import uuid
from typing import Any

from core.storage import Storage
from data.repositories import storage as storage_repo
from retrieval import layout

# Kept in sync with user-api's storage limits (backend/services/apis/user-api/handler.py).
STORAGE_MAX_FILES = 10
STORAGE_MAX_FILE_BYTES = 30 * 1024 * 1024  # 30 MB per file
STORAGE_MAX_BYTES = 100 * 1024 * 1024  # 100 MB per user

DEFAULT_READ_CHARS = 20_000
MAX_READ_CHARS = 200_000

# Best-effort content type inferred from a file name when the caller omits one.
_CONTENT_TYPES = {
    ".json": "application/json",
    ".html": "text/html",
    ".htm": "text/html",
    ".xml": "application/xml",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
}


def _clamp(value: Any, default: int, low: int, high: int) -> int:
    if isinstance(value, bool) or value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _storage() -> Storage:
    return Storage()


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    payload["error"].update({key: value for key, value in extra.items() if value is not None})
    return payload


def _safe_filename(name: str) -> str:
    base = os.path.basename(str(name or "")).strip()
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip()
    base = base.lstrip(".") or "file"
    return base[:180]


def _default_content_type(file_name: str, encoding: str) -> str:
    inferred = _CONTENT_TYPES.get(os.path.splitext(file_name)[1].lower())
    if inferred:
        return inferred
    return "application/octet-stream" if encoding == "base64" else "text/plain"


def _serialize(item: dict[str, Any], *, download_url: str | None = None) -> dict[str, Any]:
    payload = {
        "id": item.get("fileId"),
        "fileName": item.get("fileName"),
        "contentType": item.get("contentType"),
        "sizeBytes": int(item.get("sizeBytes") or 0),
        "status": item.get("status"),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }
    if download_url:
        payload["downloadUrl"] = download_url
    return payload


def _usage(user_id: str) -> tuple[int, int]:
    files = storage_repo.list_files(user_id)
    return len(files), sum(int(item.get("sizeBytes") or 0) for item in files)


def _usage_payload(user_id: str) -> dict[str, Any]:
    count, used = _usage(user_id)
    return {
        "fileCount": count,
        "storageBytes": used,
        "limits": {
            "maxFiles": STORAGE_MAX_FILES,
            "maxFileBytes": STORAGE_MAX_FILE_BYTES,
            "maxStorageBytes": STORAGE_MAX_BYTES,
        },
    }


def _ensure_capacity(user_id: str, size_bytes: int) -> dict[str, Any] | None:
    count, used = _usage(user_id)
    if count >= STORAGE_MAX_FILES:
        return _error("storage_full", f"You can store at most {STORAGE_MAX_FILES} files")
    if size_bytes > STORAGE_MAX_FILE_BYTES:
        return _error(
            "file_too_large",
            f"Each file can be at most {STORAGE_MAX_FILE_BYTES // (1024 * 1024)} MB",
        )
    if used + size_bytes > STORAGE_MAX_BYTES:
        return _error("storage_full", "You have reached your storage limit")
    return None


def _infer_format(content_type: str, data: bytes) -> str:
    media = (content_type or "").split(";")[0].strip().lower()
    if media in ("application/json", "application/ld+json") or media.endswith("+json"):
        return "json"
    if media.startswith("text/") or media in ("application/xml", "application/javascript"):
        return "text"
    try:
        data.decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        return "base64"


# --- tools -------------------------------------------------------------------


def list_files(user_id: str) -> dict[str, Any]:
    """List the caller's stored files (uploaded or written)."""
    files = storage_repo.list_files(user_id)
    return {
        "files": [_serialize(item) for item in files],
        "usage": _usage_payload(user_id),
        "error": None,
    }


def read_file(user_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Read one of the caller's stored files back by id."""
    file_id = str(params.get("fileId") or "").strip()
    if not file_id:
        return _error("invalid_request", "fileId is required")
    item = storage_repo.get_file(user_id, file_id)
    if item is None:
        return _error("not_found", "File not found")

    key = str(item.get("s3Key") or "")
    if not key:
        return _error("not_found", "File has no stored object")
    try:
        data = _storage().get_bytes(key)
    except Exception:  # noqa: BLE001
        return _error("read_failed", "Could not read the file")

    fmt = str(params.get("format") or "auto").lower()
    if fmt not in ("auto", "text", "json", "base64"):
        fmt = "auto"
    content_type = str(item.get("contentType") or "")
    if fmt == "auto":
        fmt = _infer_format(content_type, data)

    max_chars = _clamp(params.get("maxChars"), DEFAULT_READ_CHARS, 1000, MAX_READ_CHARS)
    if fmt == "json":
        try:
            content = json.dumps(json.loads(data.decode("utf-8")), indent=2, default=str)
        except (ValueError, UnicodeDecodeError):
            fmt = "text"
            content = data.decode("utf-8", "replace")
    elif fmt == "text":
        content = data.decode("utf-8", "replace")
    else:
        content = base64.b64encode(data).decode("ascii")

    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]

    return {
        "file": _serialize(item),
        "format": fmt,
        "content": content,
        "truncated": truncated,
        "sizeBytes": int(item.get("sizeBytes") or len(data)),
        "error": None,
    }


def write_file(user_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Write a new file (text or base64) into the caller's storage."""
    if not str(params.get("fileName") or "").strip():
        return _error("invalid_request", "fileName is required")
    file_name = _safe_filename(params.get("fileName"))

    raw = params.get("content")
    if raw is None:
        return _error("invalid_request", "content is required")

    encoding = str(params.get("encoding") or "text").lower()
    if encoding not in ("text", "base64"):
        return _error("invalid_request", "encoding must be 'text' or 'base64'")

    if encoding == "base64":
        try:
            data = base64.b64decode(str(raw), validate=True)
        except (ValueError, TypeError):
            return _error("invalid_request", "content is not valid base64")
    else:
        data = str(raw).encode("utf-8")

    size = len(data)
    capacity_error = _ensure_capacity(user_id, size)
    if capacity_error:
        return capacity_error

    content_type = str(params.get("contentType") or "").strip() or _default_content_type(
        file_name, encoding
    )
    file_id = str(uuid.uuid4())
    key = layout.storage_key(user_id, file_id, file_name)

    storage = _storage()
    storage.put_bytes(key, data, content_type)
    item = storage_repo.storage_item(
        file_id=file_id,
        user_id=user_id,
        file_name=file_name,
        s3_key=key,
        content_type=content_type,
        size_bytes=size,
        content_hash=hashlib.sha256(data).hexdigest(),
    )
    try:
        storage_repo.put_file(item)
    except Exception:  # noqa: BLE001 - roll back the orphaned object
        try:
            storage.delete(key)
        except Exception:  # noqa: BLE001
            pass
        return _error("conflict", "Could not save the file")

    return {
        "file": _serialize(item, download_url=storage.presign_get(key)),
        "usage": _usage_payload(user_id),
        "error": None,
    }


def delete_file(user_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Delete one of the caller's stored files and its S3 object."""
    file_id = str(params.get("fileId") or "").strip()
    if not file_id:
        return _error("invalid_request", "fileId is required")
    item = storage_repo.get_file(user_id, file_id)
    if item is None:
        return _error("not_found", "File not found")

    key = str(item.get("s3Key") or "")
    if key:
        try:
            _storage().delete(key)
        except Exception:  # noqa: BLE001 - metadata deletion must still proceed
            pass
    storage_repo.delete_file(user_id, file_id)
    return {
        "deleted": True,
        "fileId": file_id,
        "usage": _usage_payload(user_id),
        "error": None,
    }
