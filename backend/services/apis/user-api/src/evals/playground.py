"""Prompt playground: replay an LLM call with an edited prompt.

Loads nothing itself — the API layer hands it a model + messages (usually lifted
from a real trace generation) and it makes one Amazon Bedrock (Converse) call,
returning the output plus usage/latency so the UI can diff it against the
original trace output.
"""

from __future__ import annotations

import time
from typing import Any

MAX_MESSAGES = 40
MAX_MESSAGE_CHARS = 20_000
MAX_TOKENS_CAP = 8_000
DEFAULT_MAX_TOKENS = 1_024
ROLES = ("system", "user", "assistant")


class PlaygroundError(Exception):
    """The replay call could not be produced."""


def _clean_messages(messages: Any) -> list[dict[str, str]]:
    if not isinstance(messages, list):
        raise PlaygroundError("messages must be a list")
    cleaned: list[dict[str, str]] = []
    for entry in messages[:MAX_MESSAGES]:
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role") or "user").strip().lower()
        if role not in ROLES:
            role = "user"
        content = str(entry.get("content") or "")[:MAX_MESSAGE_CHARS]
        cleaned.append({"role": role, "content": content})
    if not cleaned:
        raise PlaygroundError("Provide at least one message")
    return cleaned


def run_completion(
    *,
    model: str,
    messages: Any,
    temperature: Any = 0.0,
    max_tokens: Any = DEFAULT_MAX_TOKENS,
) -> dict[str, Any]:
    if not model:
        raise PlaygroundError("Pick a model")
    cleaned = _clean_messages(messages)
    try:
        temp = min(max(float(temperature), 0.0), 2.0)
    except (TypeError, ValueError):
        temp = 0.0
    try:
        tokens = min(max(int(max_tokens), 1), MAX_TOKENS_CAP)
    except (TypeError, ValueError):
        tokens = DEFAULT_MAX_TOKENS

    system = "\n\n".join(
        entry["content"] for entry in cleaned if entry["role"] == "system"
    )
    turns = [entry for entry in cleaned if entry["role"] in ("user", "assistant")]

    from core import bedrock_chat

    started = time.perf_counter()
    try:
        result = bedrock_chat.converse(
            system, turns, model=model, max_tokens=tokens, temperature=temp
        )
    except Exception as exc:  # noqa: BLE001
        raise PlaygroundError(f"Model call failed: {exc}") from exc
    latency_ms = int((time.perf_counter() - started) * 1000)

    usage = result.get("usage") or {}
    return {
        "model": model,
        "output": str(result.get("text") or ""),
        "finishReason": result.get("stopReason"),
        "usage": {
            "input": usage.get("inputTokens"),
            "output": usage.get("outputTokens"),
            "total": usage.get("totalTokens"),
        },
        "latencyMs": latency_ms,
    }
