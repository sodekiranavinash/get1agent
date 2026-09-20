"""Build the Strands model bound to the OpenCode Go gateway.

Go is OpenAI-compatible for the models we expose (``/chat/completions``), so the
built-in Strands ``OpenAIModel`` pointed at Go's base URL works unchanged.

Go asks every client to identify itself with a descriptive user agent and to
send a stable per-conversation session id, so it can route and cache prompts
efficiently. Both are attached as default headers on the OpenAI client.
https://opencode.ai/docs/go/#where-can-i-use-it

Keep ``SUPPORTED_MODELS`` in sync with ``SUPPORTED_AGENT_MODELS`` in
``backend/services/user-api/handler.py`` and ``AGENT_MODELS`` in the frontend.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from agentflow.config import RuntimeConfig

DEFAULT_MODEL = "mimo-v2.5"
SUPPORTED_MODELS = (
    "mimo-v2.5",
    "glm-5.3-flash",
    "qwen3.8-flash",
    "deepseek-v4-flash-vision-exp",
    "gpt-5.6-luna",
    "kimi-k2.6",
)

# Models Go serves through the OpenAI Responses API instead of chat completions.
RESPONSES_MODELS = ("gpt-5.6-luna",)

# OpenCode Go requires a descriptive client user agent and a stable session id
# header (``x-opencode-session``) for routing and prompt caching.
CLIENT_USER_AGENT = "get1agent/1.0"
SESSION_HEADER = "x-opencode-session"

# Context window (tokens) per model, used for the context meter and to trigger
# proactive summarization before a call would overflow. Override any of them with
# ``AGENT_CONTEXT_WINDOW_<MODEL_ID_UPPER_SNAKE>`` or the whole default with
# ``AGENT_CONTEXT_WINDOW``.
DEFAULT_CONTEXT_WINDOW = int(os.environ.get("AGENT_CONTEXT_WINDOW", "128000"))
_CONTEXT_WINDOWS: dict[str, int] = {
    "mimo-v2.5": 128_000,
    "glm-5.3-flash": 128_000,
    "qwen3.8-flash": 128_000,
    "deepseek-v4-flash-vision-exp": 128_000,
    "gpt-5.6-luna": 1_050_000,
    "kimi-k2.6": 256_000,
}


def context_window_limit(model_id: str) -> int:
    override = os.environ.get(
        "AGENT_CONTEXT_WINDOW_" + re.sub(r"[^A-Za-z0-9]+", "_", model_id).upper()
    )
    if override and override.isdigit():
        return int(override)
    return _CONTEXT_WINDOWS.get(model_id, DEFAULT_CONTEXT_WINDOW)


def resolve_model_id(model_id: str | None) -> str:
    """Return a supported Go model, falling back for legacy/unknown ids.

    Agents saved before the model catalogue changed can carry ids such as
    ``claude-sonnet-4`` that the gateway's chat-completions endpoint rejects.
    """
    model = (model_id or "").strip()
    if model in SUPPORTED_MODELS:
        return model
    if model:
        print(
            json.dumps(
                {
                    "level": "warning",
                    "message": "Unsupported agent model; falling back",
                    "requested": model,
                    "using": DEFAULT_MODEL,
                }
            ),
            flush=True,
        )
    return DEFAULT_MODEL


def build_model(
    config: RuntimeConfig, model_id: str, session_id: str | None = None
) -> Any:
    if not config.opencode_api_key:
        raise RuntimeError("OPENCODE_API_KEY is not configured")
    headers = {"user-agent": CLIENT_USER_AGENT}
    if session_id:
        headers[SESSION_HEADER] = str(session_id)
    client_args = {
        "api_key": config.opencode_api_key,
        "base_url": config.opencode_base_url,
        "default_headers": headers,
    }

    if model_id in RESPONSES_MODELS:
        from strands.models.openai_responses import OpenAIResponsesModel

        return OpenAIResponsesModel(
            client_args=client_args,
            model_id=model_id,
            context_window_limit=context_window_limit(model_id),
        )

    from strands.models.openai import OpenAIModel

    return OpenAIModel(
        client_args=client_args,
        model_id=model_id,
        context_window_limit=context_window_limit(model_id),
    )
