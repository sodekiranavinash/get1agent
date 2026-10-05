"""http-fetch service logic (no MCP/AWS-transport dependencies).

The server exposes exactly one tool, ``http-fetch``: it calls a public http(s)
URL or API endpoint in trusted code (never the user sandbox) and returns the
response inline — JSON parsed, text decoded, binary base64-encoded — capped at a
configurable size.

It deliberately has **no storage capability**. Saving/reading files is the
separate ``storage`` MCP server; ``http-fetch`` only reaches the network and
returns what it gets.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from . import fetcher

DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 60
DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MB returned by default
MAX_MAX_BYTES = 10 * 1024 * 1024  # hard cap
DEFAULT_MAX_CHARS = 200_000
MAX_MAX_CHARS = 400_000


def _clamp(value: Any, default: int, low: int, high: int) -> int:
    if isinstance(value, bool) or value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    payload["error"].update(
        {key: value for key, value in extra.items() if value is not None}
    )
    return payload


def _infer_format(content_type: str, data: bytes) -> str:
    media = (content_type or "").split(";")[0].strip().lower()
    if media in ("application/json", "application/ld+json") or media.endswith("+json"):
        return "json"
    if media.startswith("text/") or media in (
        "application/xml",
        "application/javascript",
    ):
        return "text"
    try:
        data.decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        return "base64"


def _decode(
    content_type: str, data: bytes, fmt: str, max_chars: int
) -> tuple[str, Any, bool]:
    """Return ``(format, content, truncated)`` for a response body."""
    if fmt == "auto":
        fmt = _infer_format(content_type, data)
    if fmt == "json":
        try:
            return "json", json.loads(data.decode("utf-8")), False
        except (ValueError, UnicodeDecodeError):
            fmt = "text"
    if fmt == "base64":
        text = base64.b64encode(data).decode("ascii")
    else:
        fmt = "text"
        text = data.decode("utf-8", "replace")
    truncated = len(text) > max_chars
    return fmt, (text[:max_chars] if truncated else text), truncated


def fetch(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch ``params['url']`` and return the response inline."""
    url = str(params.get("url") or "").strip()
    if not url:
        return _error("invalid_request", "url is required")

    method = str(params.get("method") or "GET").upper()
    headers = params.get("headers") if isinstance(params.get("headers"), dict) else {}
    body = params.get("body")
    body_bytes = str(body).encode("utf-8") if body is not None else None
    timeout = _clamp(params.get("timeoutSeconds"), DEFAULT_TIMEOUT, 1, MAX_TIMEOUT)
    max_bytes = _clamp(params.get("maxBytes"), DEFAULT_MAX_BYTES, 1024, MAX_MAX_BYTES)
    max_chars = _clamp(params.get("maxChars"), DEFAULT_MAX_CHARS, 1000, MAX_MAX_CHARS)
    fmt = str(params.get("format") or "auto").lower()
    if fmt not in ("auto", "text", "json", "base64"):
        fmt = "auto"

    try:
        result = fetcher.fetch(
            url,
            method=method,
            headers={str(k): str(v) for k, v in headers.items()},
            body=body_bytes,
            timeout=timeout,
            max_bytes=max_bytes,
        )
    except fetcher.FetchError as exc:
        return _error(exc.code, exc.message)

    if not result.body:
        return _error("empty_response", "The response had an empty body")

    content_type = (result.content_type or "").split(";")[0].strip()
    decoded_format, content, truncated = _decode(
        content_type, result.body, fmt, max_chars
    )
    return {
        "status": result.status,
        "url": result.final_url,
        "requestedUrl": url,
        "contentType": content_type,
        "format": decoded_format,
        "content": content,
        "truncated": bool(truncated or result.truncated),
        "bytes": len(result.body),
        "redirects": result.redirects,
        "error": None,
    }
