"""Build Strands tools for an agent from its MCP-server + knowledge selection.

Built-in servers (``web-search``, ``code-interpreter``, ``http-fetch``) and remote servers
(through the ``mcp-connections`` aggregator) are exposed over the shared
``core.mcp_client`` direct-invoke transport. Knowledge retrieval exposes the
knowledge server's real tools (``get-user-knowledge-bases`` +
``search-user-knowledge-bases``) bound to the agent's KB names and rerank
setting, so the model cannot query KBs the agent did not attach.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from core import mcp_client

from agentflow.config import RuntimeConfig


def _slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", (value or "").lower()).strip("-")
    return slug or fallback


def _tool_specs(function: str, user_id: str) -> list[dict[str, Any]]:
    _, response = mcp_client.list_tools(function, user_id)
    result = (response or {}).get("result") or {}
    tools = result.get("tools")
    return tools if isinstance(tools, list) else []


def _text_of(response: dict[str, Any]) -> str:
    result = (response or {}).get("result") or {}
    content = result.get("content")
    if isinstance(content, list):
        texts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("text")
        ]
        if texts:
            return "\n".join(texts)
    if "text" in result:
        return str(result["text"])
    return json.dumps(result) if result else ""


def _make_tool(
    name: str,
    description: str,
    fn: Callable[[dict[str, Any]], str],
    input_schema: dict[str, Any] | None = None,
) -> Any:
    """Build a Strands tool from an MCP tool spec.

    The wrapper accepts ``**kwargs`` and forwards them to the MCP call; the real
    JSON schema is passed through ``inputSchema`` so the model sees the correct
    arguments (a ``**kwargs`` signature alone produces a bogus schema).
    """
    from strands import tool as strands_tool

    def implementation(**kwargs: Any) -> str:
        return fn(kwargs)

    # Keep the exact MCP tool name (hyphens are valid OpenAI function-name
    # characters) so the UI shows the same name the server exposes. Names with
    # characters the model API rejects (e.g. the ``/`` in remote ``slug/tool``)
    # fall back to a sanitized form.
    tool_name = name if re.fullmatch(r"[a-zA-Z0-9_-]+", name) else re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    # ``__name__`` drives Strands' internal Pydantic model name, so it must be a
    # valid identifier even when the public tool name contains hyphens.
    implementation.__name__ = re.sub(r"[^a-zA-Z0-9_]", "_", tool_name)
    implementation.__doc__ = description or f"Call the {name} tool."
    tool = strands_tool(
        implementation,
        name=tool_name,
        description=implementation.__doc__,
        inputSchema=input_schema or {"type": "object", "properties": {}},
    )
    # Strands builds its input-validation model from the wrapper's ``**kwargs``
    # signature, which would demand a single ``kwargs`` field and mangle the real
    # arguments. The MCP ``inputSchema`` is the actual contract, so bypass the
    # signature validation and forward the model's arguments verbatim.
    tool._metadata.validate_input = (  # type: ignore[attr-defined]
        lambda tool_input, *_args, **_kwargs: dict(tool_input)
    )
    return tool


def _number_sources(text: str, counter: dict[str, int]) -> str:
    """Tag every source in a tool result with a run-global ``index``.

    Knowledge search returns a ``sources`` list and web search a ``results``
    list; each item gets the next number so the model can cite it inline as
    ``[n]`` and the UI can show the same number.
    """
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return text
    if not isinstance(payload, dict):
        return text

    changed = False
    index_by_doc: dict[tuple[Any, Any], int] = {}
    for key in ("sources", "results"):
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("index") is None:
                counter["n"] += 1
                item["index"] = counter["n"]
                changed = True
            document_id = item.get("documentId")
            if document_id is not None:
                index_by_doc[(document_id, item.get("page"))] = item["index"]

    # Mirror the citation number onto the matching content chunks so the model
    # sees the same number next to the text it is citing.
    chunks = payload.get("chunks")
    if isinstance(chunks, list) and index_by_doc:
        for chunk in chunks:
            if not isinstance(chunk, dict) or chunk.get("index") is not None:
                continue
            match = index_by_doc.get((chunk.get("documentId"), chunk.get("page")))
            if match is not None:
                chunk["index"] = match
                changed = True

    return json.dumps(payload, default=str) if changed else text


# The gateway namespaces every target's tools as "<target>___<tool>". These are
# the target names created in Terraform for each server family.
_GATEWAY_TARGETS = {
    "knowledge": "knowledge",
    "code-interpreter": "code-interpreter",
    "http-fetch": "http-fetch",
    "browser": "browser",
    "custom-tools": "custom-tools",
    "remote-mcp": "remote-mcp",
}


def _gateway_tool_name(target: str, tool_name: str) -> str:
    """Fully-qualified gateway tool name for a target's tool."""
    resolved = _GATEWAY_TARGETS.get(target, target)
    return f"{resolved}___{tool_name}" if resolved else tool_name


def _mcp_caller(
    function: str,
    user_id: str,
    tool_name: str,
    counter: dict[str, int],
    guard: Callable[[str, dict[str, Any]], tuple[bool, str]] | None = None,
    gateway_url: str = "",
    session_id: str = "",
    gateway_tool_name: str = "",
) -> Callable[[dict[str, Any]], str]:
    def call(arguments: dict[str, Any]) -> str:
        if guard is not None:
            allowed, reason = guard(tool_name, arguments)
            if not allowed:
                return f"Blocked by policy: {reason}"
        if gateway_url:
            response = mcp_client.gateway_call_tool(
                gateway_url, session_id, gateway_tool_name or tool_name, arguments
            )
        else:
            _, response = mcp_client.call_tool(function, user_id, tool_name, arguments)
        return _number_sources(_text_of(response), counter)

    return call


def _knowledge_caller(
    function: str,
    user_id: str,
    tool_name: str,
    knowledge_names: list[str],
    rerank: bool,
    counter: dict[str, int],
    guard: Callable[[str, dict[str, Any]], tuple[bool, str]] | None = None,
    gateway_url: str = "",
    session_id: str = "",
    gateway_tool_name: str = "",
) -> Callable[[dict[str, Any]], str]:
    """Call a knowledge MCP tool scoped to the agent's attached KBs.

    The agent cannot query knowledge bases it did not attach: the KB names are
    always injected, overriding whatever the model passes.
    """

    def call(arguments: dict[str, Any]) -> str:
        payload = dict(arguments)
        payload["knowledgeBaseNames"] = knowledge_names
        if tool_name == "search-user-knowledge-bases":
            payload["rerank"] = rerank
        if guard is not None:
            allowed, reason = guard(tool_name, payload)
            if not allowed:
                return f"Blocked by policy: {reason}"
        if gateway_url:
            response = mcp_client.gateway_call_tool(
                gateway_url, session_id, gateway_tool_name or tool_name, payload
            )
        else:
            _, response = mcp_client.call_tool(function, user_id, tool_name, payload)
        return _number_sources(_text_of(response), counter)

    return call


_WEB_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Required. Natural-language description of the information you "
                "want (max 200 characters)."
            ),
        },
        "maxResults": {
            "type": "integer",
            "minimum": 1,
            "maximum": 25,
            "description": "How many ranked sources to return (1-25).",
        },
        "excludeDomains": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Domains to exclude from the results.",
        },
    },
    "required": ["query"],
}


def _web_search_args(arguments: dict[str, Any]) -> dict[str, Any]:
    """Map tool arguments onto the AgentCore WebSearch connector input."""
    args: dict[str, Any] = {"query": str(arguments.get("query") or "").strip()[:200]}
    raw = arguments.get("maxResults", arguments.get("numResults"))
    try:
        if raw is not None:
            args["maxResults"] = max(1, min(int(raw), 25))
    except (TypeError, ValueError):
        pass
    excludes = arguments.get("excludeDomains")
    if isinstance(excludes, list):
        clean = [str(domain).strip() for domain in excludes if str(domain).strip()]
        if clean:
            args["filters"] = {"domainFilter": {"exclude": clean}}
    return args


def _web_search_tool(
    gateway_url: str,
    session_id: str,
    gateway_tool: str,
    gateway_region: str,
    counter: dict[str, int],
    guard: Callable[[str, dict[str, Any]], tuple[bool, str]] | None,
) -> Any:
    """The gateway's built-in Web Search connector, as one Strands tool."""

    def call(arguments: dict[str, Any]) -> str:
        args = _web_search_args(arguments)
        if not args.get("query"):
            return json.dumps({"error": {"code": "invalid_request", "message": "query is required"}})
        if guard is not None:
            allowed, reason = guard("web-search", args)
            if not allowed:
                return f"Blocked by policy: {reason}"
        response = mcp_client.gateway_call_tool(
            gateway_url, session_id, gateway_tool, args, region=gateway_region or None
        )
        return _number_sources(_text_of(response), counter)

    return _make_tool(
        "web-search",
        (
            "Search the public web for current information via Amazon Bedrock "
            "AgentCore Web Search. Returns ranked sources with titles, URLs and "
            "snippets. Describe what you want in natural language."
        ),
        call,
        _WEB_SEARCH_SCHEMA,
    )


def build_tools(
    config: RuntimeConfig,
    user_id: str,
    agent_config: dict[str, Any],
    knowledge_names: list[str],
    counter: dict[str, int] | None = None,
    guard: Callable[[str, dict[str, Any]], tuple[bool, str]] | None = None,
    session_id: str = "",
) -> list[Any]:
    """Build the Strands tools for an agent.

    ``guard`` (built by :func:`agentflow.memory.build_guard`) is the AgentCore
    Policy admission check; when present every tool call is evaluated before the
    MCP server is invoked, and a denial is returned to the model as a policy error.
    """
    tools: list[Any] = []
    # When the AgentCore Gateway is configured, every MCP tool call goes through
    # it (managed MCP endpoint, Policy enforced, SigV4). Otherwise the in-app
    # servers are invoked directly (local development).
    gateway_url = config.gateway_url if config.mcp_transport == "gateway" else ""
    # Run-global citation counter: every source across every tool call gets the
    # next number, so the model's inline ``[n]`` matches the UI's source list.
    # A workflow passes one shared counter so citations stay globally numbered
    # across every agent node.
    if counter is None:
        counter = {"n": 0}

    if knowledge_names and config.knowledge_function:
        rerank = bool(agent_config.get("knowledgeRerank"))
        # Expose the knowledge server's real tools under their exact names
        # (``get-user-knowledge-bases`` + ``search-user-knowledge-bases``),
        # scoped to the agent's attached knowledge bases.
        for spec in _tool_specs(config.knowledge_function, user_id):
            tool_name = str(spec.get("name") or "")
            if tool_name not in ("get-user-knowledge-bases", "search-user-knowledge-bases"):
                continue
            schema = spec.get("inputSchema")
            if not isinstance(schema, dict):
                schema = {"type": "object", "properties": {}}
            tools.append(
                _make_tool(
                    tool_name,
                    str(spec.get("description") or ""),
                    _knowledge_caller(
                        config.knowledge_function,
                        user_id,
                        tool_name,
                        knowledge_names,
                        rerank,
                        counter,
                        guard,
                        gateway_url,
                        session_id,
                        _gateway_tool_name("knowledge", tool_name),
                    ),
                    schema,
                )
            )

    for server in agent_config.get("servers") or []:
        source = str(server.get("source") or "")
        server_id = str(server.get("id") or "")
        if source == "builtin" and server_id == "web-search":
            # Web Search is the AgentCore Gateway built-in connector — no MCP
            # Lambda and no model access. Prefer its dedicated gateway (which may
            # be in another Region); fall back to the main gateway. There is
            # deliberately no direct-invoke fallback.
            web_search_url = config.web_search_gateway_url or gateway_url
            if web_search_url:
                tools.append(
                    _web_search_tool(
                        web_search_url,
                        session_id,
                        config.web_search_gateway_tool,
                        config.web_search_gateway_region,
                        counter,
                        guard,
                    )
                )
            continue
        if source == "builtin" and server_id == "code-interpreter":
            function = config.code_interpreter_function
            gateway_target = "code-interpreter"
        elif source == "builtin" and server_id == "http-fetch":
            function = config.http_fetch_function
            gateway_target = "http-fetch"
        elif source == "builtin" and server_id == "browser":
            function = config.browser_function
            gateway_target = "browser"
        elif source == "custom":
            # User-defined Playground tools; the server id is the tool namespace.
            function = config.custom_tools_function
            gateway_target = "custom-tools"
        elif source == "mcp":
            function = config.remote_function
            gateway_target = "remote-mcp"
        else:
            continue
        if not function:
            continue

        selected = server.get("tools")
        # Custom tools are namespaced by the server slug (== its id); remote
        # tools by the slug of the connection's display name.
        prefix = server_id if source == "custom" else _slug(str(server.get("name") or ""), "")
        for spec in _tool_specs(function, user_id):
            tool_name = str(spec.get("name") or "")
            if not tool_name:
                continue
            if selected is not None:
                if tool_name not in selected:
                    continue
            elif source in ("mcp", "custom") and prefix and not tool_name.startswith(
                f"{prefix}/"
            ):
                continue
            schema = spec.get("inputSchema")
            if not isinstance(schema, dict):
                schema = {"type": "object", "properties": {}}
            tools.append(
                _make_tool(
                    tool_name,
                    str(spec.get("description") or ""),
                    _mcp_caller(
                        function,
                        user_id,
                        tool_name,
                        counter,
                        guard,
                        gateway_url,
                        session_id,
                        _gateway_tool_name(gateway_target, tool_name),
                    ),
                    schema,
                )
            )

    return tools
