"""Thin MCP JSON-RPC client for the ``knowledge-mcp`` Lambda.

``knowledge-mcp`` supports a direct-invoke transport: send a JSON-RPC message
plus the caller's internal ``userId`` and it returns the raw JSON-RPC response.
This module builds the standard MCP messages (``tools/list``, ``tools/call``)
and invokes the function with boto3 — no third-party MCP SDK or HTTP transport
needed, and the caller's identity travels in the payload.
"""

from __future__ import annotations

import json
import os
from typing import Any

# Protocol version sent on gateway calls. The AgentCore Gateway currently
# supports ``2025-03-26``; override with ``MCP_PROTOCOL_VERSION`` if it moves.
MCP_PROTOCOL_VERSION = (os.environ.get("MCP_PROTOCOL_VERSION") or "2025-03-26").strip()


class McpClientError(Exception):
    """The MCP Lambda could not be invoked or returned an unusable payload."""


def _invoke(
    function_name: str,
    message: dict[str, Any],
    region: str | None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    import boto3
    from botocore.config import Config

    kwargs: dict[str, Any] = {"region_name": region}
    if user_agent:
        kwargs["config"] = Config(user_agent_extra=user_agent)
    client = boto3.client("lambda", **kwargs)
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
    function_name: str, user_id: str, region: str | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(request, response)`` for an MCP ``tools/list`` call."""
    message = _message("tools/list", {}, 1)
    response = _invoke(function_name, {**message, "userId": user_id}, region)
    return message, response


def call_tool(
    function_name: str,
    user_id: str,
    name: str,
    arguments: dict[str, Any],
    region: str | None = None,
    user_agent: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(request, response)`` for an MCP ``tools/call`` invocation."""
    message = _message("tools/call", {"name": name, "arguments": arguments}, 2)
    response = _invoke(function_name, {**message, "userId": user_id}, region, user_agent)
    return message, response


def gateway_call_tool(
    gateway_url: str,
    session_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    region: str | None = None,
) -> dict[str, Any]:
    """Invoke a tool on the AgentCore Gateway and return its JSON-RPC response.

    The gateway speaks Streamable HTTP MCP with **SigV4** (``AWS_IAM`` authorizer),
    so the runtime signs the request with its own role. Responses are JSON or an
    SSE stream; both are normalized to a single JSON-RPC object.
    """
    import boto3
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    from botocore.exceptions import HTTPClientError
    from botocore.httpsession import URLLib3Session

    message = _message("tools/call", {"name": tool_name, "arguments": arguments}, 2)
    body = json.dumps(message).encode("utf-8")
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": MCP_PROTOCOL_VERSION,
    }
    if session_id:
        headers["mcp-session-id"] = session_id

    request = AWSRequest(method="POST", url=gateway_url, data=body, headers=headers)
    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise McpClientError("no AWS credentials for the gateway request")
    SigV4Auth(credentials, "bedrock-agentcore", region or "ap-south-1").add_auth(request)

    try:
        response = URLLib3Session().send(request.prepare())
        raw = response.content
    except HTTPClientError as exc:  # pragma: no cover - network failure path
        raise McpClientError(f"gateway request failed: {exc}") from exc

    if response.status_code >= 400:
        detail = raw[:500].decode("utf-8", "replace")
        raise McpClientError(f"gateway returned HTTP {response.status_code}: {detail}")

    return _parse_mcp_body(raw)


def _parse_mcp_body(raw: bytes) -> dict[str, Any]:
    """Normalize a JSON or SSE MCP response into one JSON-RPC object."""
    text = raw.decode("utf-8", "replace").strip()
    if not text:
        return {}
    if text.startswith("{"):
        try:
            return json.loads(text)
        except ValueError as exc:
            raise McpClientError("gateway returned invalid JSON") from exc
    # SSE: take the last `data:` frame that parses as a JSON-RPC object.
    last: dict[str, Any] | None = None
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        chunk = line[len("data:") :].strip()
        if not chunk or chunk == "[DONE]":
            continue
        try:
            parsed = json.loads(chunk)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            last = parsed
    if last is None:
        raise McpClientError("gateway returned no JSON-RPC payload")
    return last


def gateway_list_tools(
    gateway_url: str,
    session_id: str,
    region: str | None = None,
) -> dict[str, Any]:
    """Return the JSON-RPC response for an MCP ``tools/list`` call via gateway."""
    import boto3
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    from botocore.exceptions import HTTPClientError
    from botocore.httpsession import URLLib3Session

    message = _message("tools/list", {}, 1)
    body = json.dumps(message).encode("utf-8")
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": MCP_PROTOCOL_VERSION,
    }
    if session_id:
        headers["mcp-session-id"] = session_id

    request = AWSRequest(method="POST", url=gateway_url, data=body, headers=headers)
    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise McpClientError("no AWS credentials for the gateway request")
    SigV4Auth(credentials, "bedrock-agentcore", region or "ap-south-1").add_auth(request)

    try:
        response = URLLib3Session().send(request.prepare())
        raw = response.content
    except HTTPClientError as exc:  # pragma: no cover - network failure path
        raise McpClientError(f"gateway request failed: {exc}") from exc

    if response.status_code >= 400:
        detail = raw[:500].decode("utf-8", "replace")
        raise McpClientError(f"gateway returned HTTP {response.status_code}: {detail}")

    return _parse_mcp_body(raw)


def list_tools_multi(
    function_names: list[str], user_id: str, region: str | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """List tools across several MCP servers.

    Returns ``(tools, per_server)``: the merged tool list (each tool tagged with
    the ``server`` function name) and one entry per server with its raw
    ``request``/``response`` for inspection.
    """
    tools: list[dict[str, Any]] = []
    per_server: list[dict[str, Any]] = []
    for function_name in function_names:
        request, response = list_tools(function_name, user_id, region)
        per_server.append(
            {"function": function_name, "request": request, "response": response}
        )
        for tool in response.get("result", {}).get("tools", []) or []:
            if isinstance(tool, dict):
                tools.append({**tool, "server": function_name})
    return tools, per_server


def find_tool_server(
    function_names: list[str], user_id: str, tool_name: str, region: str | None = None
) -> str | None:
    """Return the MCP server that exposes ``tool_name``, if any."""
    for function_name in function_names:
        _, response = list_tools(function_name, user_id, region)
        tools = response.get("result", {}).get("tools", []) or []
        if any(isinstance(tool, dict) and tool.get("name") == tool_name for tool in tools):
            return function_name
    return None
