"""Curated OpenAI-compatible provider presets for the Vault.

A preset only pre-fills the create dialog (base URL + a suggested model list)
and tells the tester how to authenticate and where the models/chat endpoints
live. Users are always free to choose ``custom``, supply any base URL and edit
the model list — the value is only ever validated for safety (https, no private
address) and tested against ``/models``.
"""

from __future__ import annotations

from typing import Any

DEFAULT_AUTH_STYLE = "bearer"

# ``kind`` values: "provider" (has a base URL + chat models) or "generic".
KIND_PROVIDER = "provider"
KIND_GENERIC = "generic"

PRESET_PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "openai",
        "label": "OpenAI",
        "description": "OpenAI platform (GPT models) and any OpenAI-compatible endpoint.",
        "baseUrl": "https://api.openai.com/v1",
        "defaultModel": "gpt-4o-mini",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "o4-mini"],
        "requiresKey": True,
        "docsUrl": "https://platform.openai.com/api-keys",
    },
    {
        "id": "opencode",
        "label": "OpenCode Go",
        "description": "The OpenCode Go gateway used by this workspace's agents.",
        "baseUrl": "https://opencode.ai/zen/go/v1",
        "defaultModel": "deepseek-v4-flash-vision-exp",
        "models": [
            "mimo-v2.5",
            "glm-5.3-flash",
            "qwen3.8-flash",
            "deepseek-v4-flash-vision-exp",
            "gpt-5.6-luna",
            "kimi-k2.6",
        ],
        "requiresKey": True,
        "docsUrl": "https://opencode.ai",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "description": "One key for hundreds of models across providers.",
        "baseUrl": "https://openrouter.ai/api/v1",
        "defaultModel": "openai/gpt-4o-mini",
        "models": [
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
            "anthropic/claude-sonnet-4",
            "google/gemini-2.0-flash",
            "meta-llama/llama-3.3-70b-instruct",
        ],
        "requiresKey": True,
        "docsUrl": "https://openrouter.ai/keys",
    },
    {
        "id": "anthropic",
        "label": "Anthropic (Claude)",
        "description": "Claude models via Anthropic's API.",
        "baseUrl": "https://api.anthropic.com/v1",
        "defaultModel": "claude-sonnet-4-20250514",
        "models": [
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
            "claude-3-5-haiku-20241022",
        ],
        "auth": "x-api-key",
        "requiresKey": True,
        "docsUrl": "https://console.anthropic.com/settings/keys",
    },
    {
        "id": "google",
        "label": "Google Gemini",
        "description": "Gemini via Google's OpenAI-compatible endpoint.",
        "baseUrl": "https://generativelanguage.googleapis.com/v1beta/openai",
        "defaultModel": "gemini-2.0-flash",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        "requiresKey": True,
        "docsUrl": "https://aistudio.google.com/app/apikey",
    },
    {
        "id": "groq",
        "label": "Groq",
        "description": "Very fast open-model inference.",
        "baseUrl": "https://api.groq.com/openai/v1",
        "defaultModel": "llama-3.3-70b-versatile",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
        ],
        "requiresKey": True,
        "docsUrl": "https://console.groq.com/keys",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "description": "DeepSeek chat and reasoning models.",
        "baseUrl": "https://api.deepseek.com/v1",
        "defaultModel": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "requiresKey": True,
        "docsUrl": "https://platform.deepseek.com/api_keys",
    },
    {
        "id": "mistral",
        "label": "Mistral",
        "description": "Mistral's OpenAI-compatible API.",
        "baseUrl": "https://api.mistral.ai/v1",
        "defaultModel": "mistral-large-latest",
        "models": ["mistral-large-latest", "mistral-small-latest", "codestral-latest"],
        "requiresKey": True,
        "docsUrl": "https://console.mistral.ai/api-keys",
    },
    {
        "id": "together",
        "label": "Together AI",
        "description": "Hosted open-source models.",
        "baseUrl": "https://api.together.xyz/v1",
        "defaultModel": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "models": [
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "Qwen/Qwen2.5-72B-Instruct-Turbo",
        ],
        "requiresKey": True,
        "docsUrl": "https://api.together.ai/settings/api-keys",
    },
    {
        "id": "xai",
        "label": "xAI (Grok)",
        "description": "Grok models via xAI's OpenAI-compatible API.",
        "baseUrl": "https://api.x.ai/v1",
        "defaultModel": "grok-2-latest",
        "models": ["grok-2-latest", "grok-beta"],
        "requiresKey": True,
        "docsUrl": "https://console.x.ai",
    },
    {
        "id": "fireworks",
        "label": "Fireworks AI",
        "description": "Fast hosted open models.",
        "baseUrl": "https://api.fireworks.ai/inference/v1",
        "defaultModel": "accounts/fireworks/models/llama-v3p3-70b-instruct",
        "models": [
            "accounts/fireworks/models/llama-v3p3-70b-instruct",
            "accounts/fireworks/models/qwen2p5-72b-instruct",
        ],
        "requiresKey": True,
        "docsUrl": "https://fireworks.ai/account/api-keys",
    },
    {
        "id": "perplexity",
        "label": "Perplexity",
        "description": "Search-grounded chat models.",
        "baseUrl": "https://api.perplexity.ai",
        "defaultModel": "sonar",
        "models": ["sonar", "sonar-pro", "sonar-reasoning"],
        "requiresKey": True,
        "docsUrl": "https://www.perplexity.ai/settings/api",
    },
    {
        "id": "ollama",
        "label": "Ollama (local)",
        "description": "A local Ollama server on your network.",
        "baseUrl": "http://localhost:11434/v1",
        "defaultModel": "llama3.2",
        "models": ["llama3.2", "qwen2.5", "mistral"],
        "requiresKey": False,
        "docsUrl": "https://ollama.com",
    },
    {
        "id": "custom",
        "label": "Custom / other",
        "description": "Any OpenAI-compatible base URL — compatible with vLLM, LiteLLM, Azure gateways, proxies.",
        "baseUrl": "",
        "defaultModel": "",
        "models": [],
        "requiresKey": True,
        "docsUrl": "",
    },
]

_BY_ID = {provider["id"]: provider for provider in PRESET_PROVIDERS}


def get_provider(provider_id: str | None) -> dict[str, Any] | None:
    if not provider_id:
        return None
    return _BY_ID.get(str(provider_id).strip().lower())


def normalize_provider(provider_id: str | None) -> dict[str, Any]:
    """Return the preset, or the ``custom`` preset for an unknown id."""
    return get_provider(provider_id) or _BY_ID["custom"]


def provider_public_list() -> list[dict[str, Any]]:
    """Presets shaped for the SPA (auth style defaults to bearer)."""
    return [
        {
            "id": provider["id"],
            "label": provider["label"],
            "description": provider["description"],
            "baseUrl": provider["baseUrl"],
            "defaultModel": provider["defaultModel"],
            "models": list(provider.get("models") or []),
            "auth": provider.get("auth", DEFAULT_AUTH_STYLE),
            "requiresKey": provider.get("requiresKey", True),
            "docsUrl": provider.get("docsUrl", ""),
        }
        for provider in PRESET_PROVIDERS
    ]


def auth_style(provider_id: str | None) -> str:
    return normalize_provider(provider_id).get("auth", DEFAULT_AUTH_STYLE)
