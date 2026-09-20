"""Normalize Strands streaming events into the runtime's SSE envelope.

The wire contract (consumed by the builder panel and the chat screen):

    {"type": "run.started",   "runId", "agentId", "sessionId"}
    {"type": "plan.started"}
    {"type": "plan",          "understanding", "subQueries": [{"query", "todos"}]}
    {"type": "text",          "data"}
    {"type": "tool.start",    "name", "toolUseId", "input"}
    {"type": "tool.input",    "toolUseId", "input"}
    {"type": "tool.stream",   "name", "data"}
    {"type": "tool.result",   "toolUseId", "status", "data", "sources"}
    {"type": "run.completed", "stopReason", "usage"}
    {"type": "run.error",     "message"}
"""

from __future__ import annotations

import json
from typing import Any


def _usage(result: Any) -> dict[str, Any]:
    metrics = getattr(result, "metrics", None)
    usage = getattr(metrics, "accumulated_usage", None) if metrics else None
    if not usage:
        return {}
    return {
        "inputTokens": getattr(usage, "inputTokens", None),
        "outputTokens": getattr(usage, "outputTokens", None),
        "totalTokens": getattr(usage, "totalTokens", None),
    }


def _content_text(content: Any) -> str:
    """Flatten a tool result's content blocks into plain text."""
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                if block:
                    parts.append(block)
                continue
            if not isinstance(block, dict):
                continue
            if block.get("text"):
                parts.append(str(block["text"]))
            elif block.get("json") is not None:
                try:
                    parts.append(json.dumps(block["json"], indent=2, default=str))
                except (TypeError, ValueError):
                    parts.append(str(block["json"]))
        return "\n".join(parts)
    if isinstance(content, str):
        return content
    return ""


def _extract_sources(text: str) -> list[dict[str, Any]]:
    """Best-effort citation sources from a tool result payload.

    Knowledge search returns a ``sources`` list (documents/pages); web search
    returns a ``results`` list (pages). Unknown payloads yield no sources.
    """
    if not text:
        return []
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return []
    if not isinstance(payload, dict):
        return []

    sources: list[dict[str, Any]] = []

    knowledge = payload.get("sources")
    if isinstance(knowledge, list):
        for item in knowledge:
            if not isinstance(item, dict):
                continue
            page = item.get("page")
            page_end = item.get("pageEnd")
            if page and page_end and page_end != page:
                location = f"pages {page}-{page_end}"
            elif page:
                location = f"page {page}"
            else:
                location = ""
            sources.append(
                {
                    "kind": "knowledge",
                    "index": item.get("index"),
                    "title": item.get("fileName") or "Document",
                    "url": item.get("sourceUrl"),
                    "documentId": item.get("documentId"),
                    "knowledgeBaseId": item.get("knowledgeBaseId"),
                    "contentType": item.get("contentType"),
                    "page": item.get("page"),
                    "subtitle": " · ".join(
                        part for part in (item.get("kbName"), location) if part
                    ),
                    "snippet": item.get("snippet"),
                }
            )

    results = payload.get("results")
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            highlights = item.get("highlights")
            snippet = highlights[0] if isinstance(highlights, list) and highlights else None
            sources.append(
                {
                    "kind": "web",
                    "index": item.get("index"),
                    "title": item.get("title") or item.get("url") or "Result",
                    "url": item.get("url"),
                    "favicon": item.get("favicon"),
                    "image": item.get("image"),
                    "subtitle": item.get("author") or item.get("publishedDate") or "",
                    "snippet": snippet,
                }
            )

    return sources


def _result_frame(tool_result: Any) -> dict[str, Any] | None:
    if not isinstance(tool_result, dict):
        return None
    data = _content_text(tool_result.get("content"))
    return {
        "type": "tool.result",
        "toolUseId": tool_result.get("toolUseId"),
        "status": tool_result.get("status") or "success",
        "data": data,
        "sources": _extract_sources(data),
    }


def _tool_results(event: Any) -> list[dict[str, Any]]:
    """Extract ``tool.result`` frames from a tool-result event.

    Strands reports completed calls in two shapes across versions:

    - ``ToolResultEvent``: ``{"type": "tool_result", "tool_result": {...}}``.
    - ``ToolResultMessageEvent``: ``{"message": {"content": [{"toolResult": {...}}]}}``.

    A message can carry several results (parallel tool calls), so this returns a
    list.
    """
    if not isinstance(event, dict):
        return []

    direct = _result_frame(event.get("tool_result"))
    if direct is not None:
        return [direct]

    message = event.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []

    results: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        frame = _result_frame(block.get("toolResult"))
        if frame is not None:
            results.append(frame)
    return results


def normalize(event: Any) -> dict[str, Any] | None:
    if not isinstance(event, dict):
        return None

    if event.get("force_stop"):
        return {
            "type": "run.error",
            "message": str(event.get("force_stop_reason") or "Agent stopped"),
        }

    data = event.get("data")
    if isinstance(data, str) and data:
        return {"type": "text", "data": data}

    # Internal reasoning/thinking is deliberately dropped: it must never reach
    # the UI or the final answer.
    current = event.get("current_tool_use")
    if isinstance(current, dict) and current.get("name"):
        return {
            "type": "tool.start",
            "name": current.get("name"),
            "toolUseId": current.get("toolUseId"),
            "input": current.get("input"),
        }

    tool_stream = event.get("tool_stream_event")
    if isinstance(tool_stream, dict):
        use = tool_stream.get("tool_use") or {}
        return {
            "type": "tool.stream",
            "name": use.get("name"),
            "toolUseId": use.get("toolUseId"),
            "data": tool_stream.get("data"),
        }

    frame = _result_frame(event.get("tool_result"))
    if frame is not None:
        return frame

    if "result" in event:
        result = event["result"]
        return {
            "type": "run.completed",
            "stopReason": str(getattr(result, "stop_reason", "") or ""),
            "usage": _usage(result),
        }

    return None


def normalize_many(event: Any) -> list[dict[str, Any]]:
    """Normalize one Strands event into zero or more wire frames.

    Most events map 1:1, but a tool-result message can carry several results and
    is therefore expanded. ``normalize`` remains the single-frame helper.
    """
    results = _tool_results(event)
    if results:
        return results
    single = normalize(event)
    return [single] if single is not None else []
