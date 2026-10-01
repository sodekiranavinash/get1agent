"""Use a user's Vault provider secret as an agent's model.

An agent may set ``config.providerSecretId`` to one of the caller's Vault
provider secrets (kind ``provider``). At run time the runtime decrypts that
secret in-process, builds an OpenAI-compatible client against the secret's base
URL + key, and (after the run) records the token totals back onto the Vault item
so usage can be shown per service.

The plaintext key never leaves the runtime and is never returned to a client or
written to a log.
"""

from __future__ import annotations

from typing import Any

from data.repositories import vault as vault_repo


class ProviderError(Exception):
    """The selected model provider is missing, incomplete or not a provider."""


def resolve_model_provider(user_id: str, secret_id: str | None) -> dict[str, Any] | None:
    """Return ``{secretId, name, apiKey, baseUrl, defaultModel}`` or ``None``.

    Raises :class:`ProviderError` when the id was set but the secret is unusable
    (deleted, wrong kind, missing key/URL) — failing loudly beats silently
    falling back to the platform key and billing the wrong account.
    """
    secret_id = str(secret_id or "").strip()
    if not secret_id:
        return None

    item = vault_repo.get_secret(user_id, secret_id)
    if item is None:
        raise ProviderError("The selected model provider no longer exists")
    if item.get("kind") != vault_repo.KIND_PROVIDER:
        raise ProviderError("The selected secret is not a model provider")

    try:
        payload = vault_repo.open_payload(user_id, item)
    except Exception as exc:  # noqa: BLE001 - core.crypto.CryptoError
        raise ProviderError("The selected model provider could not be decrypted") from exc

    api_key = (vault_repo.primary_value(payload) or "").strip()
    base_url = str(item.get("baseUrl") or "").strip()
    if not api_key:
        raise ProviderError("The selected model provider has no API key")
    if not base_url:
        raise ProviderError("The selected model provider has no base URL")

    return {
        "secretId": item.get("secretId"),
        "name": item.get("name"),
        "apiKey": api_key,
        "baseUrl": base_url,
        "defaultModel": str(item.get("defaultModel") or "").strip(),
    }


def record_provider_usage(
    user_id: str,
    secret_id: str | None,
    usage: dict[str, Any] | None,
    model: str,
) -> None:
    """Attribute a finished run's tokens to the provider secret (best-effort)."""
    if not secret_id:
        return
    usage = usage or {}
    try:
        vault_repo.record_run(
            user_id,
            secret_id,
            model=model,
            input_tokens=int(usage.get("inputTokens") or 0),
            output_tokens=int(usage.get("outputTokens") or 0),
            total_tokens=int(usage.get("totalTokens") or 0),
        )
    except Exception:  # noqa: BLE001 - accounting must never break a run
        pass
