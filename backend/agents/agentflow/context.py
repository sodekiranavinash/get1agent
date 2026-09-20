"""Bound the tool output sent to the model (the session keeps the full data).

Tool results — web search, code interpreter, remote MCP — can be very large and
are re-sent on every turn, so they dominate the context window. This module
wraps the model with a per-call view that truncates tool-result content, keeping
the most recent results intact. The Agent's own message list (and therefore the
S3 session and the conversation transcript) is never modified.

Knowledge results are exempt: they are the user's grounding data and the
knowledge tool deliberately returns page-sized context.

Knobs: ``AGENT_TOOL_RESULT_MAX_CHARS`` (default 1500) and
``AGENT_TOOL_RESULT_KEEP_FULL`` (default 2 — the most recent N tool results are
left untouched).
"""

from __future__ import annotations

import json
import os
from typing import Any

# Tool results that are the user's grounding data and must not be truncated.
EXEMPT_TOOLS = frozenset({"search-user-knowledge-bases", "get-user-knowledge-bases"})

TRUNCATION_MARKER = "\n…[truncated to save context]"


def _max_chars() -> int:
    try:
        return int(os.environ.get("AGENT_TOOL_RESULT_MAX_CHARS") or "1500")
    except ValueError:
        return 1500


def _keep_full() -> int:
    try:
        return int(os.environ.get("AGENT_TOOL_RESULT_KEEP_FULL") or "2")
    except ValueError:
        return 2


def _tool_names(messages: list[dict[str, Any]]) -> dict[str, str]:
    """Map each ``toolUseId`` to its tool name (from assistant toolUse blocks)."""
    names: dict[str, str] = {}
    for message in messages:
        for block in message.get("content") or []:
            if isinstance(block, dict) and "toolUse" in block:
                use = block.get("toolUse") or {}
                use_id = str(use.get("toolUseId") or "")
                if use_id:
                    names[use_id] = str(use.get("name") or "")
    return names


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + TRUNCATION_MARKER


def _truncate_value(value: Any, max_chars: int) -> Any:
    if isinstance(value, str):
        return _truncate(value, max_chars)
    if isinstance(value, list):
        trimmed: list[Any] = []
        for block in value:
            if isinstance(block, dict):
                block = dict(block)
                if isinstance(block.get("text"), str):
                    block["text"] = _truncate(block["text"], max_chars)
                elif block.get("json") is not None:
                    block["json"] = _truncate_json(block["json"], max_chars)
            trimmed.append(block)
        return trimmed
    return value


def _truncate_json(value: Any, max_chars: int) -> Any:
    try:
        encoded = json.dumps(value, default=str)
    except (TypeError, ValueError):
        return value
    if len(encoded) <= max_chars:
        return value
    return encoded[:max_chars] + TRUNCATION_MARKER


def trim_tool_results(
    messages: list[dict[str, Any]],
    *,
    max_chars: int | None = None,
    keep_full: int | None = None,
) -> list[dict[str, Any]]:
    """Return a copy of ``messages`` with older tool results truncated."""
    limit = max_chars if max_chars is not None else _max_chars()
    keep = keep_full if keep_full is not None else _keep_full()
    names = _tool_names(messages)

    result_indexes = [
        index
        for index, message in enumerate(messages)
        if any(
            isinstance(block, dict) and "toolResult" in block
            for block in (message.get("content") or [])
        )
    ]
    keep_indexes = set(result_indexes[-keep:]) if keep > 0 else set()

    trimmed: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        content = message.get("content") or []
        is_result = any(
            isinstance(block, dict) and "toolResult" in block for block in content
        )
        if not is_result or index in keep_indexes:
            trimmed.append(message)
            continue

        new_content: list[Any] = []
        for block in content:
            if not isinstance(block, dict) or "toolResult" not in block:
                new_content.append(block)
                continue
            result = dict(block.get("toolResult") or {})
            use_id = str(result.get("toolUseId") or "")
            if names.get(use_id) in EXEMPT_TOOLS:
                new_content.append(block)
                continue
            result["content"] = _truncate_value(result.get("content"), limit)
            new_block = dict(block)
            new_block["toolResult"] = result
            new_content.append(new_block)

        new_message = dict(message)
        new_message["content"] = new_content
        trimmed.append(new_message)

    return trimmed


class TruncatingModel:
    """A ``Model`` proxy that trims tool results before the provider call.

    Only ``stream`` and ``count_tokens`` are overridden; everything else
    (``context_window_limit``, ``config``, ``stateful``, ``structured_output``,
    ``init_agent`` …) is delegated to the wrapped model.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def stream(self, messages: list[dict[str, Any]], *args: Any, **kwargs: Any) -> Any:
        return self._inner.stream(trim_tool_results(messages), *args, **kwargs)

    async def count_tokens(
        self, messages: list[dict[str, Any]], *args: Any, **kwargs: Any
    ) -> int:
        return await self._inner.count_tokens(trim_tool_results(messages), *args, **kwargs)
