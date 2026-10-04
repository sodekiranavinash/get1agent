"""Live connection testing for a Vault provider secret.

The test runs **server-side** (never in the browser) so a provider's CORS policy
cannot block it and the key never has to be exposed to JavaScript. It uses only
the stdlib (``urllib``) plus a small SSRF guard, matching the http-fetch service:

* only ``http``/``https``;
* the hostname is resolved and every address checked against a
  loopback/private/link-local/reserved/metadata denylist (private addresses are
  only allowed when ``VAULT_ALLOW_PRIVATE_URLS=true``, e.g. for a local Ollama);
* the key is only ever placed in a request header and is never logged.

The test is deliberately cheap: ``GET /models`` confirms the key + base URL, and
(optionally) one tiny ``POST /chat/completions`` confirms the chosen model
actually answers. Providers that lack ``/models`` still pass if the chat call
succeeds.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .providers import auth_style, normalize_provider

CLIENT_USER_AGENT = "get1agent/1.0"
DEFAULT_TIMEOUT_SECONDS = 15
MAX_MODELS = 50
CHAT_PROMPT = "Reply with the single word: ok"


class TestError(Exception):
    """The provider could not be reached or rejected the credentials."""


def _timeout() -> int:
    try:
        value = int(os.environ.get("VAULT_TEST_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT_SECONDS)
    except ValueError:
        value = DEFAULT_TIMEOUT_SECONDS
    return max(3, min(value, 30))


def _allow_private() -> bool:
    return (os.environ.get("VAULT_ALLOW_PRIVATE_URLS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


# --- SSRF guard ---------------------------------------------------------------


def _validate_base_url(base_url: str) -> str:
    value = (base_url or "").strip().rstrip("/")
    if not value:
        raise TestError("A base URL is required to test this provider")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ("http", "https"):
        raise TestError("Base URL must start with http:// or https://")
    if not parsed.hostname:
        raise TestError("Base URL is missing a hostname")
    if parsed.username or parsed.password:
        raise TestError("Base URL must not contain credentials")
    if parsed.scheme == "http" and not _allow_private():
        raise TestError("Base URL must use https://")

    host = parsed.hostname
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise TestError(f"Could not resolve host '{host}'") from exc
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if _is_blocked(ip):
            raise TestError("Base URL resolves to a private or reserved address")
    return value


def _is_blocked(ip: Any) -> bool:
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
        return not _allow_private()
    if ip.is_private:
        return not _allow_private()
    # Cloud metadata endpoints.
    if ip == ipaddress.ip_address("169.254.169.254"):
        return True
    return False


# --- HTTP ---------------------------------------------------------------------


def _headers(provider_id: str | None, api_key: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "accept": "application/json",
        "user-agent": CLIENT_USER_AGENT,
    }
    style = auth_style(provider_id)
    if api_key:
        if style == "x-api-key":
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["authorization"] = f"Bearer {api_key}"
    if extra:
        headers.update(extra)
    return headers


def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    body: bytes | None = None,
    timeout: int,
) -> tuple[int, Any, str]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status, _maybe_json(raw), ""
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        return exc.code, _maybe_json(detail), detail
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TestError("Could not reach the provider — check the base URL") from exc


def _maybe_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _model_ids(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    ids: list[str] = []
    for entry in data:
        if isinstance(entry, dict) and entry.get("id"):
            ids.append(str(entry["id"]))
        elif isinstance(entry, str):
            ids.append(entry)
    return ids[:MAX_MODELS]


def _auth_message(status: int) -> str:
    if status in (401, 403):
        return "The provider rejected this key (unauthorized)"
    if status == 404:
        return "The provider has no /models endpoint here"
    if status == 429:
        return "The provider is rate limiting this key"
    if status >= 500:
        return "The provider returned a server error"
    return "The provider returned an unexpected response"


# --- public API ---------------------------------------------------------------


def test_provider(
    *,
    base_url: str,
    api_key: str = "",
    provider_id: str | None = None,
    model: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Probe a provider and return live results, or raise :class:`TestError`."""
    preset = normalize_provider(provider_id)
    resolved_id = preset["id"]
    base = _validate_base_url(base_url)
    api_key = (api_key or "").strip()
    if preset.get("requiresKey", True) and not api_key:
        raise TestError("This provider needs an API key")

    timeout = timeout or _timeout()
    started = time.perf_counter()
    headers = _headers(resolved_id, api_key)

    status, payload, _ = _request(
        "GET", f"{base}/models", headers=headers, timeout=timeout
    )
    if status in (401, 403):
        raise TestError(_auth_message(status))
    models = _model_ids(payload) if status == 200 else []

    selected_model = (model or "").strip() or str(preset.get("defaultModel") or "")
    chat: dict[str, Any] | None = None
    chat_status: int | None = None
    # Only hit chat when we have a model to try — a bare /models probe is enough
    # otherwise.
    if selected_model:
        chat_headers = _headers(
            resolved_id, api_key, {"content-type": "application/json"}
        )
        body = json.dumps(
            {
                "model": selected_model,
                "messages": [{"role": "user", "content": CHAT_PROMPT}],
                "max_tokens": 16,
                "temperature": 0,
            }
        ).encode("utf-8")
        try:
            chat_status, chat_payload, _ = _request(
                "POST",
                f"{base}/chat/completions",
                headers=chat_headers,
                body=body,
                timeout=timeout,
            )
            chat = _chat_result(chat_payload) if chat_status == 200 else None
        except TestError:
            # A chat failure on top of a good /models response is not fatal.
            chat_status = None

    latency_ms = int((time.perf_counter() - started) * 1000)

    if status == 200 or chat is not None:
        if chat is not None:
            message = f"Connected — {selected_model} replied in {latency_ms} ms"
        else:
            message = f"Connected — {len(models)} model(s) available"
        return {
            "ok": True,
            "provider": resolved_id,
            "baseUrl": base,
            "status": status,
            "latencyMs": latency_ms,
            "models": models,
            "model": selected_model or None,
            "sample": chat.get("sample") if chat else None,
            "usage": chat.get("usage") if chat else None,
            "message": message,
            "checkedAt": datetime.now(timezone.utc).isoformat(),
        }

    # Neither endpoint succeeded — surface the most useful message.
    if selected_model and chat_status:
        message = _auth_message(chat_status)
    else:
        message = _auth_message(status)
    return {
        "ok": False,
        "provider": resolved_id,
        "baseUrl": base,
        "status": status,
        "latencyMs": latency_ms,
        "models": models,
        "model": selected_model or None,
        "sample": None,
        "usage": None,
        "message": message,
        "checkedAt": datetime.now(timezone.utc).isoformat(),
    }


def list_models(
    *,
    base_url: str,
    api_key: str = "",
    provider_id: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """List a provider's models via ``GET /models`` (no chat call).

    Used by the Vault dialog's "Fetch models" action. Raises
    :class:`TestError` only when the request cannot be made at all; a rejected
    key is reported as ``ok: False`` with a message.
    """
    preset = normalize_provider(provider_id)
    resolved_id = preset["id"]
    base = _validate_base_url(base_url)
    api_key = (api_key or "").strip()
    if preset.get("requiresKey", True) and not api_key:
        raise TestError("This provider needs an API key")

    timeout = timeout or _timeout()
    started = time.perf_counter()
    status, payload, _ = _request(
        "GET", f"{base}/models", headers=_headers(resolved_id, api_key), timeout=timeout
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    if status == 200:
        return {
            "ok": True,
            "status": status,
            "latencyMs": latency_ms,
            "models": _model_ids(payload),
            "message": "Models loaded",
        }
    return {
        "ok": False,
        "status": status,
        "latencyMs": latency_ms,
        "models": [],
        "message": _auth_message(status),
    }


def _chat_result(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    sample = ""
    if isinstance(message, dict):
        sample = str(message.get("content") or "")[:200]
    return {"sample": sample, "usage": payload.get("usage")}
