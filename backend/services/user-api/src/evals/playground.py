"""Prompt playground: replay an LLM call with an edited prompt.

Loads nothing itself — the API layer hands it a model + messages (usually lifted
from a real trace generation) and it makes one OpenCode Go ``/chat/completions``
call, returning the output plus usage/latency so the UI can diff it against the
original trace output.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

from . import config

CLIENT_USER_AGENT = "get1agent/1.0"
SESSION_HEADER = "x-opencode-session"

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
    api_key = config.opencode_api_key()
    if not api_key:
        raise PlaygroundError("The model gateway is not configured")
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

    body = json.dumps(
        {
            "model": model,
            "messages": cleaned,
            "temperature": temp,
            "max_tokens": tokens,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{config.opencode_base_url()}/chat/completions",
        data=body,
        method="POST",
        headers={
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": CLIENT_USER_AGENT,
            SESSION_HEADER: str(uuid.uuid4()),
        },
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(
            request, timeout=min(config.llm_timeout(), 25)
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise PlaygroundError(f"Model call failed ({exc.code}): {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PlaygroundError("Model call timed out") from exc
    except ValueError as exc:
        raise PlaygroundError("Model returned an invalid response") from exc
    latency_ms = int((time.perf_counter() - started) * 1000)

    try:
        choice = payload["choices"][0]
        content = str(choice["message"]["content"])
        finish = choice.get("finish_reason")
    except (KeyError, IndexError, TypeError) as exc:
        raise PlaygroundError("Model returned no content") from exc

    usage = payload.get("usage") or {}
    return {
        "model": model,
        "output": content,
        "finishReason": finish,
        "usage": {
            "input": usage.get("prompt_tokens"),
            "output": usage.get("completion_tokens"),
            "total": usage.get("total_tokens"),
        },
        "latencyMs": latency_ms,
    }
