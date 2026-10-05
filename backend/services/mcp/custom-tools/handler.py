"""custom-tools MCP server Lambda.

Serves the Python tools a user defined in the Playground as an MCP server,
namespaced ``<serverSlug>/<toolName>`` (mirroring the remote aggregator). The
tool set is per-user and loaded on every request, so a tool saved in the
Playground is immediately usable by an agent.

Execution is delegated to the shared sandbox (``core.sandbox``): AgentCore
Code Interpreter in production, a guarded local subprocess under Floci.

Besides the MCP transport it exposes a direct-invoke ``{"action": "test"}``
payload used by ``user-api`` to run an unsaved draft (no persistence).
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable

from awslabs.mcp_lambda_handler import MCPLambdaHandler

from core.mcp_server import build_handler, current_sub
from core.storage import Storage

from data.repositories import custom_tools as repo
from data.repositories.users import get_user_by_sub

from src import config, execute

# Code is immutable per (key, hash); cache it in the warm container to avoid a
# repeated S3 read on every tool call.
_CODE_CACHE: dict[str, str] = {}
_CODE_CACHE_MAX = 64


def _log(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, default=str), flush=True)


def _load_code(code_key: str, code_hash: str) -> str:
    cache_key = f"{code_key}:{code_hash}"
    cached = _CODE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    code = Storage().get_text(code_key)
    if len(_CODE_CACHE) >= _CODE_CACHE_MAX:
        _CODE_CACHE.pop(next(iter(_CODE_CACHE)), None)
    _CODE_CACHE[cache_key] = code
    return code


def _bounded(value: Any, limit: int) -> Any:
    try:
        text = json.dumps(value, default=str)
    except (TypeError, ValueError):
        text = json.dumps({"result": str(value)})
    if len(text) <= limit:
        return value
    return {"truncated": True, "preview": text[:limit]}


def _caller(tool: dict[str, Any]) -> Callable[..., Any]:
    """Build the MCP implementation for one stored tool."""

    def call(**arguments: Any) -> str:
        user_id = current_sub()
        if not user_id:
            return json.dumps({"ok": False, "error": {"code": "no_user", "message": "No user"}})
        try:
            code = _load_code(str(tool["codeKey"]), str(tool.get("codeHash") or ""))
        except Exception as exc:  # noqa: BLE001 - missing source must not 500
            _log("custom-tool code load failed", tool=tool.get("name"), error=str(exc))
            return json.dumps(
                {"ok": False, "error": {"code": "code_unavailable", "message": "Tool source is unavailable"}}
            )
        result = execute.run_tool(
            user_id,
            code=code,
            args=arguments,
            input_schema=tool.get("inputSchema"),
            output_schema=tool.get("outputSchema"),
            entrypoint=str(tool.get("entrypoint") or "run"),
            log=_log,
        )
        if result.get("ok"):
            result["result"] = _bounded(result.get("result"), config.max_result_chars())
        return json.dumps(result, default=str)

    return call


class CustomToolsHandler(MCPLambdaHandler):
    """Aggregates a user's custom tools into one MCP surface."""

    def __init__(self, name: str, version: str = "1.0.0") -> None:
        super().__init__(name=name, version=version)
        self._dynamic: set[str] = set()

    def handle_request(self, event: dict[str, Any], context: Any) -> dict[str, Any]:
        user_id = current_sub()
        if user_id:
            try:
                self._load_tools(user_id)
            except Exception as exc:  # noqa: BLE001 - never fail the request on a load error
                _log("custom-tools load failed", error=str(exc))
        return super().handle_request(event, context)

    def _load_tools(self, user_id: str) -> None:
        for name in list(self._dynamic):
            self.tools.pop(name, None)
            self.tool_implementations.pop(name, None)
        self._dynamic.clear()

        for tool in repo.list_all_tools(user_id):
            slug = str(tool.get("serverSlug") or "").strip()
            tool_name = str(tool.get("name") or "").strip()
            if not slug or not tool_name:
                continue
            name = f"{slug}/{tool_name}"
            schema = tool.get("inputSchema")
            if not isinstance(schema, dict):
                schema = {"type": "object", "properties": {}}
            self.tools[name] = {
                "name": name,
                "description": str(tool.get("description") or ""),
                "inputSchema": schema,
            }
            self.tool_implementations[name] = _caller(tool)
            self._dynamic.add(name)


def _resolve_user_id(sub: str) -> str | None:
    """Map the HTTP caller's Auth0 sub to the internal userId."""
    try:
        profile = get_user_by_sub(sub)
    except Exception:  # noqa: BLE001 - fall through to an unauthenticated tool error
        return None
    return str(profile["userId"]) if profile else None


mcp_server = CustomToolsHandler("get1agent-custom-tools")
_mcp_lambda_handler = build_handler(mcp_server, resolve_user_id=_resolve_user_id)


def _handle_test(event: dict[str, Any]) -> dict[str, Any]:
    """Run an unsaved (or saved) tool draft. Direct invoke, IAM-trusted."""
    user_id = str(event.get("userId") or "").strip()
    if not user_id:
        return {"ok": False, "error": {"code": "no_user", "message": "userId is required"}}
    args = event.get("args")
    if not isinstance(args, dict):
        args = {}
    try:
        result = execute.run_tool(
            user_id,
            code=str(event.get("code") or ""),
            args=args,
            input_schema=event.get("inputSchema"),
            output_schema=event.get("outputSchema"),
            entrypoint=str(event.get("entrypoint") or "run"),
            is_test=True,
            conversation_id=str(event.get("conversationId") or "test"),
            log=_log,
        )
    except Exception as exc:  # noqa: BLE001
        _log("custom-tool test failed", error=repr(exc))
        return {"ok": False, "error": {"code": "internal_error", "message": str(exc)}}
    if result.get("ok"):
        result["result"] = _bounded(result.get("result"), config.max_result_chars())
    return result


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    if isinstance(event, dict) and event.get("action") == "test":
        try:
            return _handle_test(event)
        except Exception as exc:  # noqa: BLE001
            print(f"custom-tools test error: {exc!r}", file=sys.stderr)
            traceback.print_exc()
            return {"ok": False, "error": {"code": "internal_error", "message": "Test failed"}}
    return _mcp_lambda_handler(event, context)
