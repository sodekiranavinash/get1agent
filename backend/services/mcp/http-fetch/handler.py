"""http-fetch MCP server Lambda.

Exposes exactly one tool, ``http-fetch``: call a public http(s) URL or API
endpoint from trusted code and return the response inline (JSON parsed, text
decoded, binary base64-encoded).

It has **no storage capability** — listing, reading and writing the user's files
is the separate ``storage`` MCP server. The fetch runs outside a VPC (public
internet) with a per-request SSRF guard, so private/loopback/internal hosts are
refused.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from awslabs.mcp_lambda_handler import MCPLambdaHandler

from core.mcp_server import build_handler
from core import network

from src import service

mcp = MCPLambdaHandler(name="get1agent-http-fetch", version="1.0.0")

FETCH_TOOL = "http-fetch"

_FETCH_SCHEMA: dict[str, Any] = {
    "name": FETCH_TOOL,
    "description": (
        "Call a public http(s) URL or API endpoint and return its response "
        "inline (JSON is parsed, text returned as text, binary base64-encoded; "
        "large bodies are truncated). Supports GET/POST/PUT/PATCH/DELETE/HEAD "
        "with optional headers and body. This tool only reaches the network and "
        "returns the response — it does not save anything. To persist the "
        "result, pass it to the storage server's write-storage-file. Only public "
        "addresses are reachable (private/loopback/internal hosts are refused)."
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
            "format": {
                "type": "string",
                "enum": ["auto", "text", "json", "base64"],
                "description": "How to return the body (default auto-detect).",
            },
            "timeoutSeconds": {
                "type": "integer",
                "description": "Request timeout in seconds (default 30, max 60).",
            },
            "maxBytes": {
                "type": "integer",
                "description": "Maximum response bytes to return (default 2 MB, max 10 MB).",
            },
            "maxChars": {
                "type": "integer",
                "description": "Maximum characters of a text/JSON body to return (default 200000).",
            },
        },
        "required": ["url"],
    },
}


def http_fetch(
    url: str,
    method: str | None = None,
    headers: dict[str, Any] | None = None,
    body: str | None = None,
    format: str | None = None,
    timeoutSeconds: int | None = None,
    maxBytes: int | None = None,
    maxChars: int | None = None,
) -> str:
    """Fetch a URL and return the response inline (no storage)."""
    if not network.enabled():
        return json.dumps(
            service._error(
                "network_disabled",
                "Network access is disabled for this workspace by an administrator.",
            ),
            default=str,
        )
    params = {
        "url": url,
        "method": method,
        "headers": headers,
        "body": body,
        "format": format,
        "timeoutSeconds": timeoutSeconds,
        "maxBytes": maxBytes,
        "maxChars": maxChars,
    }
    try:
        result = service.fetch(params)
    except Exception as exc:  # noqa: BLE001
        print(f"{FETCH_TOOL} error: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        result = service._error("internal_error", "Request failed")
    return json.dumps(result, default=str)


mcp.tools[FETCH_TOOL] = _FETCH_SCHEMA
mcp.tool_implementations[FETCH_TOOL] = http_fetch


lambda_handler = build_handler(mcp)
