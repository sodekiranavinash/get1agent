"""http-fetch service logic (no MCP/AWS-transport dependencies).

The server exposes three tools:

* ``http-fetch`` — fetch a URL/API endpoint (HTML, JSON, text, …) in trusted
  code and store the response in the caller's S3 storage area. It returns the
  stored file's metadata, never the bytes (the caller reads them back with
  ``read-storage-file``).
* ``list-storage-files`` — list the caller's stored files.
* ``read-storage-file`` — read one stored file (fetched or uploaded) back as
  text, parsed JSON or base64.

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
import urllib.parse
import uuid
from typing import Any

from core.storage import Storage
from data.repositories import storage as storage_repo
from retrieval import layout

from . import fetcher

# Kept in sync with user-api's storage limits (backend/services/user-api/handler.py).
STORAGE_MAX_FILES = 10
STORAGE_MAX_FILE_BYTES = 30 * 1024 * 1024  # 30 MB per file
STORAGE_MAX_BYTES = 100 * 1024 * 1024  # 100 MB per user

DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 60
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_READ_CHARS = 20_000
MAX_READ_CHARS = 200_000

_TEXT_TYPES = ("text/", "application/json", "application/xml", "application/javascript")
_EXTENSIONS = {
    "application/json": ".json",
    "application/ld+json": ".json",
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "text/xml": ".xml",
    "application/xml": ".xml",
    "text/csv": ".csv",
    "text/plain": ".txt",
    "application/pdf": ".pdf",
}


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _allowed_domains() -> tuple[str, ...]:
    raw = _env("HTTP_FETCH_ALLOWED_DOMAINS")
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


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


def _extension_for(content_type: str, url: str) -> str:
    path_ext = os.path.splitext(urllib.parse.urlsplit(url).path)[1]
    if 1 < len(path_ext) <= 6 and path_ext[1:].isalnum():
        return path_ext
    media = (content_type or "").split(";")[0].strip().lower()
    if media in _EXTENSIONS:
        return _EXTENSIONS[media]
    if media.startswith("text/"):
        return ".txt"
    if media.endswith("+json"):
        return ".json"
    if media.endswith("+xml"):
        return ".xml"
    return ".bin"


def _name_from_url(url: str, content_type: str) -> str:
    path = urllib.parse.urlsplit(url).path.rstrip("/")
    candidate = os.path.basename(path) or "response"
    if not os.path.splitext(candidate)[1]:
        candidate = candidate + _extension_for(content_type, url)
    return _safe_filename(candidate)


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


# --- tools -------------------------------------------------------------------


def fetch_and_save(user_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Fetch ``params['url']`` and store the response in the user's storage."""
    url = str(params.get("url") or "").strip()
    if not url:
        return _error("invalid_request", "url is required")

    method = str(params.get("method") or "GET").upper()
    headers = params.get("headers") if isinstance(params.get("headers"), dict) else {}
    body = params.get("body")
    body_bytes = str(body).encode("utf-8") if body is not None else None
    timeout = _clamp(params.get("timeoutSeconds"), DEFAULT_TIMEOUT, 1, MAX_TIMEOUT)
    max_bytes = min(
        _clamp(params.get("maxBytes"), DEFAULT_MAX_BYTES, 1024, STORAGE_MAX_FILE_BYTES),
        STORAGE_MAX_FILE_BYTES,
    )

    try:
        result = fetcher.fetch(
            url,
            method=method,
            headers={str(k): str(v) for k, v in headers.items()},
            body=body_bytes,
            timeout=timeout,
            max_bytes=max_bytes,
            allowed_domains=_allowed_domains(),
        )
    except fetcher.FetchError as exc:
        return _error(exc.code, exc.message)

    if result.truncated:
        return _error(
            "response_too_large",
            f"The response exceeded {max_bytes // (1024 * 1024)} MB and was not saved",
        )
    if not result.body:
        return _error("empty_response", "The response had an empty body")

    size = len(result.body)
    capacity_error = _ensure_capacity(user_id, size)
    if capacity_error:
        return capacity_error

    content_type = (result.content_type or "application/octet-stream").split(";")[0].strip()
    file_name = _safe_filename(
        params.get("fileName") or _name_from_url(result.final_url, content_type)
    )
    file_id = str(uuid.uuid4())
    key = layout.storage_key(user_id, file_id, file_name)

    storage = _storage()
    storage.put_bytes(key, result.body, content_type)
    item = storage_repo.storage_item(
        file_id=file_id,
        user_id=user_id,
        file_name=file_name,
        s3_key=key,
        content_type=content_type,
        size_bytes=size,
        content_hash=hashlib.sha256(result.body).hexdigest(),
    )
    try:
        storage_repo.put_file(item)
    except Exception:  # noqa: BLE001 - roll back the orphaned object
        try:
            storage.delete(key)
        except Exception:  # noqa: BLE001
            pass
        return _error("conflict", "Could not save the fetched file")

    return {
        "file": _serialize(item, download_url=storage.presign_get(key)),
        "request": {
            "url": url,
            "finalUrl": result.final_url,
            "method": method,
            "status": result.status,
            "contentType": content_type,
            "redirects": result.redirects,
        },
        "usage": _usage_payload(user_id),
        "error": None,
    }


def list_files(user_id: str) -> dict[str, Any]:
    """List the caller's stored files (fetched or uploaded)."""
    files = storage_repo.list_files(user_id)
    return {
        "files": [_serialize(item) for item in files],
        "usage": _usage_payload(user_id),
        "error": None,
    }


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
