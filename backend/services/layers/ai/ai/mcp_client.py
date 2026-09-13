"""Thin MCP JSON-RPC client for the ``knowledge-mcp`` Lambda.

``knowledge-mcp`` supports a direct-invoke transport: send a JSON-RPC message
plus the caller's ``auth0Sub`` and it returns the raw JSON-RPC response. This
module builds the standard MCP messages (``tools/list``, ``tools/call``) and
invokes the function with boto3 — no third-party MCP SDK or HTTP transport
needed, and the caller's identity travels in the payload.
"""

from __future__ import annotations

import json
from typing import Any


class McpClientError(Exception):
    """The MCP Lambda could not be invoked or returned an unusable payload."""


def _invoke(function_name: str, message: dict[str, Any], region: str | None) -> dict[str, Any]:
    import boto3

    client = boto3.client("lambda", region_name=region)
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(message).encode("utf-8"),
    )
    raw = response["Payload"].read()
    if response.get("FunctionError"):
        detail = raw[:500].decode("utf-8", "replace")
        raise McpClientError(f"{function_name} failed: {detail}")
    try:
        parsed = json.loads(raw or b"{}")
    except ValueError as exc:
        raise McpClientError(f"{function_name} returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise McpClientError(f"{function_name} returned a non-object response")
    return parsed


def _message(method: str, params: dict[str, Any], request_id: int) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def list_tools(
    function_name: str, sub: str, region: str | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(request, response)`` for an MCP ``tools/list`` call."""
    message = _message("tools/list", {}, 1)
    response = _invoke(function_name, {**message, "auth0Sub": sub}, region)
    return message, response


def call_tool(
    function_name: str,
    sub: str,
    name: str,
    arguments: dict[str, Any],
    region: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(request, response)`` for an MCP ``tools/call`` invocation."""
    message = _message("tools/call", {"name": name, "arguments": arguments}, 2)
    response = _invoke(function_name, {**message, "auth0Sub": sub}, region)
    return message, response
