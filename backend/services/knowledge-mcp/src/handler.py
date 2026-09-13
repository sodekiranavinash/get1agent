from __future__ import annotations

import json
import os
import sys
import traceback
from contextvars import ContextVar
from typing import Any

from awslabs.mcp_lambda_handler import MCPLambdaHandler

from ai.auth import AuthError, require_user

mcp = MCPLambdaHandler(name="get1agent-knowledge", version="1.0.0")

# The MCP handler does not hand the raw event to tool functions, so identity is
# stashed here for the duration of the request (Lambda serves one at a time).
_current_sub: ContextVar[str | None] = ContextVar("current_sub", default=None)

GET_TOOL = "get-user-knowledge-bases"
SEARCH_TOOL = "search-user-knowledge-bases"

_GET_SCHEMA: dict[str, Any] = {
    "name": GET_TOOL,
    "description": (
        "List the user's ready knowledge bases with their tags (and tag "
        "descriptions). Use this first to discover which knowledge base names "
        "and tags exist before searching. Returns a compact list only; use "
        "search-user-knowledge-bases for document content."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "knowledgeBaseNames": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Knowledge base names to fetch. Omit to list all ready "
                    "knowledge bases."
                ),
            },
        },
    },
}

_SEARCH_SCHEMA: dict[str, Any] = {
    "name": SEARCH_TOOL,
    "description": (
        "Hybrid (semantic + keyword) search across the user's knowledge bases. "
        "Returns the most relevant context with its sources. Each result's "
        "`content` is the full page/section the match came from (use this to "
        "answer) and `matchedContent` is the precise passage that matched. "
        "Optionally rerank results with Amazon Bedrock for higher precision. "
        "Always use this to ground answers in the user's documents."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural-language search query.",
            },
            "knowledgeBaseNames": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Knowledge base names to search. Omit to search all.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Document tag names to filter by. A document matches if it "
                    "has any of the given tags."
                ),
            },
            "rerank": {
                "type": "boolean",
                "description": (
                    "Rerank the results with Amazon Bedrock Rerank for higher "
                    "precision. Defaults to false."
                ),
            },
        },
        "required": ["query"],
    },
}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _require_sub() -> str:
    sub = _current_sub.get()
    if not sub:
        raise RuntimeError("No authenticated user in request context")
    return sub


def _invoke(function_env: str, payload: dict[str, Any]) -> dict[str, Any]:
    function_name = os.environ.get(function_env)
    if not function_name:
        raise RuntimeError(f"{function_env} is not set")

    import boto3

    client = boto3.client("lambda", region_name=os.environ.get("AWS_REGION"))
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    raw = response["Payload"].read()
    if response.get("FunctionError"):
        detail = raw[:500].decode("utf-8", "replace")
        raise RuntimeError(f"{function_name} failed: {detail}")
    try:
        return json.loads(raw or b"{}")
    except ValueError as exc:
        raise RuntimeError(f"{function_name} returned invalid JSON") from exc


def get_user_knowledge_bases(
    knowledgeBaseNames: list[str] | None = None,
) -> str:
    """Return the user's ready knowledge bases with their tags."""
    result = _invoke(
        "GET_USER_KB_FUNCTION",
        {
            "auth0Sub": _require_sub(),
            "knowledgeBaseNames": _as_list(knowledgeBaseNames),
        },
    )
    return json.dumps(result, default=str)


def search_user_knowledge_bases(
    query: str,
    knowledgeBaseNames: list[str] | None = None,
    tags: list[str] | None = None,
    rerank: bool = False,
) -> str:
    """Run hybrid search across the user's knowledge bases."""
    payload: dict[str, Any] = {
        "auth0Sub": _require_sub(),
        "query": query,
        "knowledgeBaseNames": _as_list(knowledgeBaseNames),
        "tags": _as_list(tags),
        "rerank": bool(rerank),
    }

    result = _invoke("SEARCH_USER_KB_FUNCTION", payload)
    return json.dumps(result, default=str)


# Register tools explicitly so optional arguments are not marked required.
mcp.tools[GET_TOOL] = _GET_SCHEMA
mcp.tool_implementations[GET_TOOL] = get_user_knowledge_bases
mcp.tools[SEARCH_TOOL] = _SEARCH_SCHEMA
mcp.tool_implementations[SEARCH_TOOL] = search_user_knowledge_bases


def _claims_sub(event: dict[str, Any]) -> str | None:
    try:
        claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
        return str(claims.get("sub") or "").strip() or None
    except (KeyError, TypeError, AttributeError):
        return None


def _claims(event: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]
    except (KeyError, TypeError, AttributeError):
        return None


def _is_http_event(event: dict[str, Any]) -> bool:
    return "body" in event and ("requestContext" in event or "httpMethod" in event)


def _json_http_error(status_code: int, message: str) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"error": message}),
    }


def _error_response(code: int, message: str, request_id: Any = None) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
        ),
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    event = event if isinstance(event, dict) else {}

    if _is_http_event(event):
        # Strict separation: admin accounts must use the admin tester, not the
        # user-facing MCP endpoint. The direct-invoke transport (used by
        # mcp-tester) is admin-only and checked by the caller.
        try:
            require_user(_claims(event), event)
        except AuthError as exc:
            return _json_http_error(exc.status, exc.message)
        _current_sub.set(_claims_sub(event))
        try:
            return mcp.handle_request(event, context)
        except Exception as exc:  # noqa: BLE001
            print(f"knowledge-mcp error: {exc!r}", file=sys.stderr)
            traceback.print_exc()
            return _error_response(-32603, "Internal error")

    # Direct Lambda invoke transport: a JSON-RPC message plus caller identity.
    sub = event.get("auth0Sub") or event.get("sub")
    _current_sub.set(str(sub).strip() if sub else None)
    message = {
        key: event[key]
        for key in ("jsonrpc", "id", "method", "params")
        if key in event
    }
    message.setdefault("jsonrpc", "2.0")
    if "method" not in message:
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "error": {"code": -32600, "message": "Invalid Request"},
        }

    try:
        response = mcp.handle_request(
            {
                "headers": {"content-type": "application/json"},
                "body": json.dumps(message),
                "httpMethod": "POST",
            },
            context,
        )
        return json.loads(response.get("body") or "{}")
    except Exception as exc:  # noqa: BLE001
        print(f"knowledge-mcp direct error: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "error": {"code": -32603, "message": "Internal error"},
        }
