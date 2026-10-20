"""Synchronous Amazon Bedrock chat helper (Converse API).

One call path for the user-api Labs (Playground, Evaluations judges, custom-tool
generation): the platform gateway is Amazon Bedrock, authenticated with IAM
(SigV4) — no API key. The agent runtime uses Strands' ``BedrockModel`` instead.

Before each call the request is admitted through :mod:`core.ratelimit_bedrock`
so the account-level Bedrock quota is respected across all Lambdas.
"""

from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_MODEL = "zai.glm-4.7-flash"


class BedrockChatError(RuntimeError):
    """A Bedrock Converse call failed or returned no text."""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def model_id() -> str:
    return _env("BEDROCK_CHAT_MODEL", DEFAULT_MODEL)


def region() -> str:
    return _env("BEDROCK_REGION") or _env("AWS_REGION") or "ap-south-1"


def _client() -> Any:
    import boto3
    from botocore.config import Config

    # A Converse call with a large ``max_tokens`` budget (the graph extractor
    # asks for 32k) can generate for well over botocore's default 60s read
    # timeout. A timeout there is retried, so one slow generation looks like a
    # stuck Lambda. Give long generations room; the caller's own timeout still
    # bounds the run.
    return boto3.client(
        "bedrock-runtime",
        region_name=region(),
        config=Config(
            retries={"max_attempts": 6, "mode": "adaptive"},
            connect_timeout=float(_env("BEDROCK_CONNECT_TIMEOUT_SECONDS") or 10),
            read_timeout=float(_env("BEDROCK_READ_TIMEOUT_SECONDS") or 180),
        ),
    )


def _workload() -> str:
    """Which workload this call belongs to (drives the application profile)."""
    return (os.environ.get("BEDROCK_WORKLOAD") or "chat").strip().lower()


def _throttle_model(target: str) -> None:
    try:
        from . import ratelimit_bedrock

        ratelimit_bedrock.throttle(target)
    except Exception:  # noqa: BLE001 - limiter must never block the call
        pass


def _cache_point() -> dict[str, Any] | None:
    """A Bedrock cache point for the system prompt, or None when disabled.

    The Labs send the same system prompt on every call (judges, generation), so
    caching it cuts repeated input cost. ``BEDROCK_PROMPT_CACHE=off`` disables.
    """
    mode = (os.environ.get("BEDROCK_PROMPT_CACHE", "auto") or "auto").strip().lower()
    if mode in ("0", "false", "no", "off", "none"):
        return None
    ttl = (os.environ.get("BEDROCK_PROMPT_CACHE_TTL") or "").strip()
    point: dict[str, Any] = {"type": "default"}
    if ttl:
        point["ttl"] = ttl
    return {"cachePoint": point}


_VALID_SERVICE_TIERS = frozenset({"priority", "default", "flex", "reserved"})


def _service_tier() -> str | None:
    tier = (os.environ.get("BEDROCK_SERVICE_TIER") or "").strip().lower()
    # The platform calls the default tier "standard"; Bedrock's API calls it
    # "default". Everything else is passed through only when the API accepts it.
    if tier == "standard":
        tier = "default"
    return tier if tier in _VALID_SERVICE_TIERS else None


def _normalize_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Bedrock Converse needs user/assistant turns starting with a user turn."""
    turns: list[dict[str, Any]] = []
    for entry in messages or []:
        role = str(entry.get("role") or "").strip().lower()
        content = str(entry.get("content") or "")
        if role not in ("user", "assistant") or not content:
            continue
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"][0]["text"] += "\n\n" + content
        else:
            turns.append({"role": role, "content": [{"text": content}]})
    if not turns:
        raise BedrockChatError("No user/assistant messages to send")
    if turns[0]["role"] != "user":
        turns.insert(0, {"role": "user", "content": [{"text": "(conversation continued)"}]})
    return turns


def _structured_value(blocks: list[Any], text: str) -> Any:
    """Extract the schema-constrained value from a Converse response.

    Bedrock returns Structured Outputs as the JSON string in the content
    ``text`` block; some models also return it as a ``json`` content block.
    """
    for block in blocks:
        if isinstance(block, dict) and isinstance(block.get("json"), (dict, list)):
            return block["json"]
    if text.strip():
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return None
    return None


def converse(
    system: str,
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.2,
    output_schema: dict[str, Any] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One Bedrock Converse call with a message list; returns a result dict.

    Pass ``output_schema`` (JSON Schema) to use **Bedrock Structured Outputs**:
    the model is constrained to emit an object matching the schema, returned as
    ``structured`` alongside the text. Use it for judges and code generation
    instead of prompt-only JSON.

    ``extra_fields`` is forwarded as ``additionalModelRequestFields`` — the
    model-specific knobs (e.g. ``{"thinking": {"type": "disabled"}}``).
    """
    target = (model or model_id()).strip() or DEFAULT_MODEL
    # Apply an application inference profile / intelligent prompt router when set.
    try:
        from . import bedrock_features

        target = bedrock_features.resolve_model(target, workload=_workload())
    except Exception:  # noqa: BLE001 - feature wiring must never block a call
        pass
    _throttle_model(target)

    kwargs: dict[str, Any] = {
        "modelId": target,
        "messages": _normalize_messages(messages),
        "inferenceConfig": {
            "maxTokens": max(int(max_tokens), 1),
            "temperature": float(temperature),
        },
    }
    if system:
        blocks: list[dict[str, Any]] = [{"text": system}]
        cache_point = _cache_point()
        if cache_point:
            blocks.append(cache_point)
        kwargs["system"] = blocks
    if output_schema:
        kwargs["outputConfig"] = {
            "textFormat": {
                "type": "json_schema",
                "structure": {
                    "jsonSchema": {
                        "schema": json.dumps(output_schema),
                        "name": "response",
                        "description": "Structured response",
                    }
                },
            }
        }
    if extra_fields:
        kwargs["additionalModelRequestFields"] = extra_fields
    tier = _service_tier()
    if tier:
        kwargs["serviceTier"] = {"type": tier}
    try:
        response = _client().converse(**kwargs)
    except Exception as exc:  # noqa: BLE001
        # Some models (and regions) reject prompt caching. When the cache point is
        # the cause, retry once without it rather than failing the whole call.
        if "prompt caching" in str(exc).lower() and "system" in kwargs:
            kwargs["system"] = [
                block
                for block in kwargs["system"]
                if not (isinstance(block, dict) and "cachePoint" in block)
            ]
            if not kwargs["system"]:
                del kwargs["system"]
            try:
                response = _client().converse(**kwargs)
            except Exception as exc2:  # noqa: BLE001
                raise BedrockChatError(str(exc2)) from exc2
        else:
            raise BedrockChatError(str(exc)) from exc

    output_message = (response.get("output") or {}).get("message") or {}
    blocks = output_message.get("content") or []
    text = "".join(
        str(block.get("text") or "")
        for block in blocks
        if isinstance(block, dict)
    )
    return {
        "text": text,
        "stopReason": response.get("stopReason"),
        "usage": response.get("usage") or {},
        "structured": _structured_value(blocks, text) if output_schema else None,
    }


def chat_result(
    system: str,
    user: str,
    *,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.2,
    output_schema: dict[str, Any] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One single-turn Bedrock Converse call; returns ``{text, stopReason, usage}``.

    Pass ``output_schema`` (JSON Schema) to use **Bedrock Structured Outputs**;
    the constrained object is returned under ``structured``.
    """
    return converse(
        system,
        [{"role": "user", "content": user}],
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        output_schema=output_schema,
        extra_fields=extra_fields,
    )


def chat(
    system: str,
    user: str,
    *,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> str:
    """One single-turn Bedrock Converse call; returns the assistant text."""
    result = chat_result(
        system, user, model=model, max_tokens=max_tokens, temperature=temperature
    )
    text = str(result.get("text") or "")
    if not text.strip():
        raise BedrockChatError("Bedrock returned no text")
    return text
