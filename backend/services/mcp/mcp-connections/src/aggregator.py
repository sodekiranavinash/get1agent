"""MCP server that aggregates a user's remote MCP tools.

Agents talk to this one endpoint (``POST /mcp/remote``) instead of every remote
server. ``tools/list`` merges the cached tool lists of every connected server,
namespaced ``<server>/<tool>``; ``tools/call`` strips the prefix and proxies the
call to the owning server with a freshly (lazily) refreshed token.

Tools are injected into the shared ``MCPLambdaHandler`` per request because the
set is per-user and dynamic. Cached tool lists live in S3 (see
``service.load_cached_tools``) so ``tools/list`` does not fan out to every
remote server on each agent turn.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Callable

from awslabs.mcp_lambda_handler import MCPLambdaHandler
from core.mcp_server import current_sub
from data.repositories import mcp_connections as repo
from data.repositories.mcp_connections import STATUS_CONNECTED

from . import service


def _slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", (value or "").lower()).strip("-")
    return slug or fallback


def _text_of(result: dict[str, Any]) -> str:
    """Flatten an MCP tool result to text for the aggregating framework."""
    content = result.get("content") if isinstance(result, dict) else None
    if isinstance(content, list):
        texts = [
            block["text"]
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ]
        if texts:
            return "\n".join(texts)
    return json.dumps(result, default=str)


def _caller(user_id: str, conn_id: str, tool_name: str) -> Callable[..., Any]:
    def call(**arguments: Any) -> Any:
        result = service.call_connection_tool(user_id, conn_id, tool_name, arguments)
        return _text_of(result)

    return call


class RemoteMCPHandler(MCPLambdaHandler):
    """Aggregates every connected remote server into one MCP surface."""

    def __init__(self, name: str, version: str = "1.0.0") -> None:
        super().__init__(name=name, version=version)
        self._dynamic: set[str] = set()

    def handle_request(self, event: dict[str, Any], context: Any) -> dict[str, Any]:
        user_id = current_sub()
        if user_id:
            try:
                self._load_tools(user_id)
            except Exception as exc:  # noqa: BLE001 - never fail the MCP request on cache errors
                print(f"remote-mcp tool load failed: {exc!r}", file=sys.stderr)
        return super().handle_request(event, context)

    def _load_tools(self, user_id: str) -> None:
        for name in list(self._dynamic):
            self.tools.pop(name, None)
            self.tool_implementations.pop(name, None)
        self._dynamic.clear()

        used: set[str] = set()
        for index, connection in enumerate(repo.list_connections(user_id)):
            if connection.get("status") != STATUS_CONNECTED:
                continue
            if connection.get("enabled") is False:
                continue
            prefix = _slug(connection.get("name") or "", f"server-{index}")
            while prefix in used:
                prefix = f"{prefix}-{index}"
            used.add(prefix)

            disabled = {str(name) for name in connection.get("disabledTools") or []}
            for tool in service.load_cached_tools(user_id, connection["connId"]):
                original = str(tool.get("name") or "").strip()
                if not original or original in disabled:
                    continue
                name = f"{prefix}/{original}"
                schema = tool.get("inputSchema")
                self.tools[name] = {
                    "name": name,
                    "description": str(tool.get("description") or ""),
                    "inputSchema": schema
                    if isinstance(schema, dict)
                    else {"type": "object", "properties": {}},
                }
                self.tool_implementations[name] = _caller(
                    user_id, connection["connId"], original
                )
                self._dynamic.add(name)
