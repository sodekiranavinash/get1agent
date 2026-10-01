"""http-fetch MCP server Lambda.

Exposes three tools as one MCP server:

* ``http-fetch`` — fetch a public URL/API endpoint (HTML, JSON, text, …) from
  trusted code and store the response in the caller's S3 storage.
* ``list-storage-files`` — list the caller's stored files.
* ``read-storage-file`` — read a stored file (fetched or uploaded) back.

The fetch runs outside a VPC (public internet) with a per-request SSRF guard;
stored files live under the caller's ``storage/<userId>/…`` prefix and are
scoped by the resolved internal userId, so one user can never read another's.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from awslabs.mcp_lambda_handler import MCPLambdaHandler

from core.mcp_server import build_handler, require_sub

from data.repositories.users import get_user_by_sub

from src import service

mcp = MCPLambdaHandler(name="get1agent-http-fetch", version="1.0.0")

FETCH_TOOL = "http-fetch"
LIST_TOOL = "list-storage-files"
READ_TOOL = "read-storage-file"

_FETCH_SCHEMA: dict[str, Any] = {
    "name": FETCH_TOOL,
    "description": (
        "Fetch a public http(s) URL or API endpoint and save the response to "
        "the user's storage, returning the stored file's id and metadata. "
        "Supports HTML, JSON, XML, CSV and other content types. Use this to "
        "call an API or download a page when web search is not enough; read "
        "the saved file with read-storage-file. Only public addresses are "
        "reachable (private/loopback/internal hosts are refused)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Absolute http(s) URL to fetch.",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
                "description": "HTTP method (default GET).",
            },
            "headers": {
                "type": "object",
                "description": (
                    "Optional request headers as a flat object, e.g. "
                    "{\"authorization\": \"Bearer …\", \"accept\": \"application/json\"}. "
                    "A 'host' header is ignored."
                ),
                "additionalProperties": {"type": "string"},
            },
            "body": {
                "type": "string",
                "description": "Optional request body (for POST/PUT/PATCH).",
            },
            "fileName": {
                "type": "string",
                "description": (
                    "Optional stored file name; derived from the URL/content "
                    "type when omitted."
                ),
            },
            "timeoutSeconds": {
                "type": "integer",
                "description": "Request timeout in seconds (default 30, max 60).",
            },
            "maxBytes": {
                "type": "integer",
                "description": (
                    "Maximum response size to store in bytes (default 10 MB, "
                    "capped at the 30 MB storage limit)."
                ),
            },
        },
        "required": ["url"],
    },
}

_LIST_SCHEMA: dict[str, Any] = {
    "name": LIST_TOOL,
    "description": (
        "List the user's stored files (both fetched responses and files the "
        "user uploaded). Returns each file's id, name, content type and size; "
        "use read-storage-file with the id to read the content."
    ),
    "inputSchema": {"type": "object", "properties": {}},
}

_READ_SCHEMA: dict[str, Any] = {
    "name": READ_TOOL,
    "description": (
        "Read one of the user's stored files by id and return its content. "
        "JSON is parsed, text is returned as text, and binary is base64-encoded."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "fileId": {
                "type": "string",
                "description": "The file id from http-fetch or list-storage-files.",
            },
            "format": {
                "type": "string",
                "enum": ["auto", "text", "json", "base64"],
                "description": "How to decode the content (default auto).",
            },
            "maxChars": {
                "type": "integer",
                "description": "Maximum characters to return (default 20000).",
            },
        },
        "required": ["fileId"],
    },
}


def _run(tool: str, fn: Any, *args: Any) -> str:
    try:
        result = fn(*args)
    except Exception as exc:  # noqa: BLE001
        print(f"{tool} error: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        result = service._error("internal_error", "Request failed")
    return json.dumps(result, default=str)


def http_fetch(
    url: str,
    method: str | None = None,
    headers: dict[str, Any] | None = None,
    body: str | None = None,
    fileName: str | None = None,
    timeoutSeconds: int | None = None,
    maxBytes: int | None = None,
) -> str:
    """Fetch a URL and save the response to the user's storage."""
    params = {
        "url": url,
        "method": method,
        "headers": headers,
        "body": body,
        "fileName": fileName,
        "timeoutSeconds": timeoutSeconds,
        "maxBytes": maxBytes,
    }
    return _run(FETCH_TOOL, service.fetch_and_save, require_sub(), params)


def list_storage_files() -> str:
    """List the user's stored files."""
    return _run(LIST_TOOL, service.list_files, require_sub())


def read_storage_file(
    fileId: str,
    format: str | None = None,
    maxChars: int | None = None,
) -> str:
    """Read one stored file by id."""
    params = {"fileId": fileId, "format": format, "maxChars": maxChars}
    return _run(READ_TOOL, service.read_file, require_sub(), params)


mcp.tools[FETCH_TOOL] = _FETCH_SCHEMA
mcp.tool_implementations[FETCH_TOOL] = http_fetch
mcp.tools[LIST_TOOL] = _LIST_SCHEMA
mcp.tool_implementations[LIST_TOOL] = list_storage_files
mcp.tools[READ_TOOL] = _READ_SCHEMA
mcp.tool_implementations[READ_TOOL] = read_storage_file


def _resolve_user_id(sub: str) -> str | None:
    """Map the HTTP caller's Auth0 sub to the internal userId for storage."""
    try:
        profile = get_user_by_sub(sub)
    except Exception:  # noqa: BLE001 - fall through to an unauthenticated tool error
        return None
    return str(profile["userId"]) if profile else None


lambda_handler = build_handler(mcp, resolve_user_id=_resolve_user_id)
