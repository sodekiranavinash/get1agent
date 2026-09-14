from __future__ import annotations

import json
import os
from typing import Any

from awslabs.mcp_lambda_handler import MCPLambdaHandler

from ai.mcp_server import build_handler, require_sub

mcp = MCPLambdaHandler(name="get1agent-knowledge", version="1.0.0")

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
            "auth0Sub": require_sub(),
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
        "auth0Sub": require_sub(),
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

lambda_handler = build_handler(mcp)
