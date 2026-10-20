"""Normalize Strands streaming events into the runtime's SSE envelope.

The wire contract (consumed by the builder panel and the chat screen):

    {"type": "run.started",   "runId", "agentId", "sessionId"}
    {"type": "skills",        "skills": [{"id", "name"}]}
    {"type": "plan.started"}
    {"type": "plan",          "understanding", "subQueries": [{"query", "todos"}]}
    {"type": "text",          "data"}
    {"type": "tool.start",    "name", "toolUseId", "input"}
    {"type": "tool.input",    "toolUseId", "input"}
    {"type": "tool.stream",   "name", "data"}
    {"type": "tool.result",   "toolUseId", "status", "data", "sources", "cache", "graph"}
    {"type": "question",      "questionId", "question", "options", "allowCustom"}
    {"type": "run.completed", "stopReason", "usage"}
    {"type": "run.error",     "message"}

The ``question`` frame is human-in-the-loop only (chat): the agent paused via a
Strands interrupt and the client resumes the same run with ``interruptResponses``.
"""

from __future__ import annotations

import json
from typing import Any


# ``accumulated_usage`` is an object in some Strands versions and a plain dict
# in others, and the keys are camelCase or snake_case depending on the version.
_USAGE_KEYS: dict[str, tuple[str, ...]] = {
    "inputTokens": ("inputTokens", "input_tokens"),
    "outputTokens": ("outputTokens", "output_tokens"),
    "totalTokens": ("totalTokens", "total_tokens"),
}

# Cap on the relationships carried on a ``tool.result`` frame: the run timeline
# shows the walked paths, it does not need the whole traversal.
_GRAPH_MAX_RELATIONSHIPS = 12


def _usage_value(usage: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        if isinstance(usage, dict):
            if usage.get(name) is not None:
                return usage[name]
        else:
            value = getattr(usage, name, None)
            if value is not None:
                return value
    return None


def accumulated_usage(usage: Any) -> dict[str, Any]:
    """Normalize an ``accumulated_usage`` (object or dict) into camelCase keys."""
    if not usage:
        return {}
    return {key: _usage_value(usage, names) for key, names in _USAGE_KEYS.items()}


def _usage(result: Any) -> dict[str, Any]:
    metrics = getattr(result, "metrics", None)
    usage = getattr(metrics, "accumulated_usage", None) if metrics else None
    if not usage and metrics is not None:
        summary = getattr(metrics, "get_summary", None)
        if callable(summary):
            try:
                usage = (summary() or {}).get("accumulated_usage")
            except Exception:  # noqa: BLE001 - a meter must never break a run
                usage = None
    return accumulated_usage(usage)


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


def _extract_cache(text: str) -> dict[str, Any] | None:
    """Cache provenance from a tool result payload's ``meta.cache``.

    Knowledge search stamps how its result was served (exact cache, semantic
    cache or computed) so the run timeline can label a result that came back
    from a cache instead of fresh work. Payloads without it yield ``None``.
    """
    if not text:
        return None
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return None
    cache = meta.get("cache")
    if not isinstance(cache, dict):
        return None

    info: dict[str, Any] = {"hit": bool(cache.get("hit"))}
    if isinstance(cache.get("kind"), str):
        info["kind"] = cache["kind"]
    if isinstance(cache.get("backend"), str):
        info["backend"] = cache["backend"]
    similarity = cache.get("similarity")
    if isinstance(similarity, (int, float)) and not isinstance(similarity, bool):
        info["similarity"] = float(similarity)
    return info


def _extract_graph(text: str) -> dict[str, Any] | None:
    """Graph provenance from a knowledge-search payload.

    A Graph-mode knowledge base answers graph-first (or falls back to the hybrid
    legs); the walked relationships and the seed/node/parent counts ride along so
    the run timeline can show *why* a passage is relevant instead of looking like
    a plain hybrid hit. Payloads without a graph run yield ``None``.
    """
    if not text:
        return None
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    meta = payload.get("meta")
    raw = meta.get("graph") if isinstance(meta, dict) else None
    relationships = payload.get("relationships")

    info: dict[str, Any] = {}
    if isinstance(raw, dict):
        for key in (
            "enabled",
            "requested",
            "strategy",
            "fallback",
            "reason",
            "seeds",
            "nodes",
            "edges",
            "parents",
        ):
            if raw.get(key) is not None:
                info[key] = raw[key]
    if isinstance(relationships, list):
        walked: list[dict[str, Any]] = []
        for item in relationships[:_GRAPH_MAX_RELATIONSHIPS]:
            if not isinstance(item, dict):
                continue
            subject = item.get("subject")
            predicate = item.get("predicate")
            target = item.get("object")
            if not (subject and predicate and target):
                continue
            walked.append(
                {
                    "subject": str(subject),
                    "predicate": str(predicate),
                    "object": str(target),
                    "hop": item.get("hop"),
                }
            )
        if walked:
            info["relationships"] = walked
    if not info.get("enabled") and not info.get("relationships"):
        return None
    return info


def _result_frame(tool_result: Any) -> dict[str, Any] | None:
    if not isinstance(tool_result, dict):
        return None
    data = _content_text(tool_result.get("content"))
    frame: dict[str, Any] = {
        "type": "tool.result",
        "toolUseId": tool_result.get("toolUseId"),
        "status": tool_result.get("status") or "success",
        "data": data,
        "sources": _extract_sources(data),
    }
    # Only present when the payload carried it, so ordinary tool results stay lean.
    cache = _extract_cache(data)
    if cache is not None:
        frame["cache"] = cache
    graph = _extract_graph(data)
    if graph is not None:
        frame["graph"] = graph
    return frame


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
