"""storage MCP server Lambda.

Exposes the caller's standalone Storage files as one MCP server:

* ``list-storage-files`` — list the caller's stored files.
* ``read-storage-file`` — read a stored file back (text, parsed JSON, base64).
* ``write-storage-file`` — write a new file (text or base64) and return its
  metadata plus a presigned download URL.
* ``delete-storage-file`` — delete a stored file and its metadata.

Files live under the caller's ``storage/<userId>/…`` prefix and are scoped by
the resolved internal userId, so one user can never read another's. This is the
agent's view of the user's files: list, read, write and delete.
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

mcp = MCPLambdaHandler(name="get1agent-storage", version="1.0.0")

LIST_TOOL = "list-storage-files"
READ_TOOL = "read-storage-file"
WRITE_TOOL = "write-storage-file"
DELETE_TOOL = "delete-storage-file"

_LIST_SCHEMA: dict[str, Any] = {
    "name": LIST_TOOL,
    "description": (
        "List the user's stored files (files they uploaded and files written "
        "by the agent). Returns each file's id, name, content type, size, "
        "status and timestamps; use read-storage-file with the id to read the "
        "content."
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
                "description": "The file id from list-storage-files.",
            },
            "format": {
                "type": "string",
                "enum": ["auto", "text", "json", "base64"],
                "description": "How to decode the content (default auto).",
            },
            "maxChars": {
                "type": "integer",
                "description": (
                    "Maximum characters to return (default 20000, max 200000)."
                ),
            },
        },
        "required": ["fileId"],
    },
}

_WRITE_SCHEMA: dict[str, Any] = {
    "name": WRITE_TOOL,
    "description": (
        "Write a new file into the user's storage and return its metadata plus "
        "a presigned download URL. Content is UTF-8 text by default; set "
        "encoding to base64 to store binary. The file appears on the user's "
        "Storage page and obeys the storage limits (10 files, 30 MB per file, "
        "100 MB total); the call fails with a typed error when a limit is "
        "exceeded."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "fileName": {
                "type": "string",
                "description": "Name for the stored file (basename is kept).",
            },
            "content": {
                "type": "string",
                "description": (
                    "File content: UTF-8 text, or base64 when encoding is "
                    "'base64'."
                ),
            },
            "contentType": {
                "type": "string",
                "description": (
                    "Optional MIME type; inferred from the file name when "
                    "omitted."
                ),
            },
            "encoding": {
                "type": "string",
                "enum": ["text", "base64"],
                "description": "How to decode content before storing (default text).",
            },
        },
        "required": ["fileName", "content"],
    },
}

_DELETE_SCHEMA: dict[str, Any] = {
    "name": DELETE_TOOL,
    "description": (
        "Delete one of the user's stored files by id, removing both the S3 "
        "object and its metadata. Returns {deleted: true, fileId}; a missing "
        "file returns a not_found error."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "fileId": {
                "type": "string",
                "description": "The file id from list-storage-files.",
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


def write_storage_file(
    fileName: str,
    content: str,
    contentType: str | None = None,
    encoding: str | None = None,
) -> str:
    """Write a new file into the user's storage."""
    params = {
        "fileName": fileName,
        "content": content,
        "contentType": contentType,
        "encoding": encoding,
    }
    return _run(WRITE_TOOL, service.write_file, require_sub(), params)


def delete_storage_file(fileId: str) -> str:
    """Delete one stored file by id."""
    params = {"fileId": fileId}
    return _run(DELETE_TOOL, service.delete_file, require_sub(), params)


mcp.tools[LIST_TOOL] = _LIST_SCHEMA
mcp.tool_implementations[LIST_TOOL] = list_storage_files
mcp.tools[READ_TOOL] = _READ_SCHEMA
mcp.tool_implementations[READ_TOOL] = read_storage_file
mcp.tools[WRITE_TOOL] = _WRITE_SCHEMA
mcp.tool_implementations[WRITE_TOOL] = write_storage_file
mcp.tools[DELETE_TOOL] = _DELETE_SCHEMA
mcp.tool_implementations[DELETE_TOOL] = delete_storage_file


def _resolve_user_id(sub: str) -> str | None:
    """Map the HTTP caller's Auth0 sub to the internal userId for storage."""
    try:
        profile = get_user_by_sub(sub)
    except Exception:  # noqa: BLE001 - fall through to an unauthenticated tool error
        return None
    return str(profile["userId"]) if profile else None


lambda_handler = build_handler(mcp, resolve_user_id=_resolve_user_id)
