"""Build Strands tools for an agent from its MCP-server + knowledge selection.

Built-in servers (``web-search``, ``code-interpreter``) and remote servers
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


def _mcp_caller(
    function: str, user_id: str, tool_name: str, counter: dict[str, int]
) -> Callable[[dict[str, Any]], str]:
    def call(arguments: dict[str, Any]) -> str:
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
        _, response = mcp_client.call_tool(function, user_id, tool_name, payload)
        return _number_sources(_text_of(response), counter)

    return call


def build_tools(
    config: RuntimeConfig,
    user_id: str,
    agent_config: dict[str, Any],
    knowledge_names: list[str],
) -> list[Any]:
    tools: list[Any] = []
    # Run-global citation counter: every source across every tool call gets the
    # next number, so the model's inline ``[n]`` matches the UI's source list.
    counter: dict[str, int] = {"n": 0}

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
                    ),
                    schema,
                )
            )

    for server in agent_config.get("servers") or []:
        source = str(server.get("source") or "")
        server_id = str(server.get("id") or "")
        if source == "builtin" and server_id == "web-search":
            function = config.web_search_function
        elif source == "builtin" and server_id == "code-interpreter":
            function = config.code_interpreter_function
        elif source == "mcp":
            function = config.remote_function
        else:
            continue
        if not function:
            continue

        selected = server.get("tools")
        prefix = _slug(str(server.get("name") or ""), "")
        for spec in _tool_specs(function, user_id):
            tool_name = str(spec.get("name") or "")
            if not tool_name:
                continue
            if selected is not None:
                if tool_name not in selected:
                    continue
            elif source == "mcp" and prefix and not tool_name.startswith(f"{prefix}/"):
                continue
            schema = spec.get("inputSchema")
            if not isinstance(schema, dict):
                schema = {"type": "object", "properties": {}}
            tools.append(
                _make_tool(
                    tool_name,
                    str(spec.get("description") or ""),
                    _mcp_caller(function, user_id, tool_name, counter),
                    schema,
                )
            )

    return tools
