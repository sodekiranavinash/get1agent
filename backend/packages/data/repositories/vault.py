"""Per-user encrypted secrets — the Vault.

One item per secret (``USER#<userId>`` / ``VAULT#<name>``). ``name`` is the
lowercase-hyphen *reference slug* used as ``{{vault:name}}`` wherever a secret
can be referenced. The secret material itself is a small JSON document
(``{"fields": {...}}``) encrypted with a dedicated KMS key via
:mod:`core.crypto`, bound to ``{userId, secretId, field}``.

This module deliberately moves opaque ciphertext around: the routing layer
never serialises ``payloadEnc`` and only ever surfaces the masked ``preview``.
Plaintext only exists inside :func:`seal_payload` / :func:`open_payload` and the
resolver. ``name`` is part of the key, so renaming deletes + conditionally
puts (mirroring the skills repository).
"""

from __future__ import annotations

import json
import re
from typing import Any

from core import crypto
from data.client import is_conditional_failure, now_iso, table
from data.keys import GSI1, META, VAULT_PREFIX, user_pk, vault_sk

# Kinds of secret. ``provider`` carries an OpenAI-compatible base URL + model;
# ``generic`` is an arbitrary named secret (token, connection string, …).
KIND_PROVIDER = "provider"
KIND_GENERIC = "generic"

# Field names whose value counts as the "primary" secret when a reference does
# not name one explicitly.
_PRIMARY_FIELDS = ("apiKey", "value", "token", "secret", "password")

# Fields are lower snake-ish identifiers so ``{{vault:name.field}}`` is readable.
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# ``{{vault:name}}`` or ``{{vault:name.field}}``.
_REF_RE = re.compile(
    r"\{\{\s*vault:([a-z0-9][a-z0-9-]{0,63})(?:\.([a-z][a-z0-9_]{0,63}))?\s*\}\}"
)


class DuplicateVaultSecret(Exception):
    """A secret with this name already exists for the user."""


class VaultReferenceError(Exception):
    """A ``{{vault:…}}`` reference could not be resolved."""


# --- payload (de)serialisation ----------------------------------------------


def seal_payload(user_id: str, secret_id: str, fields: dict[str, str]) -> str:
    """Encrypt the secret's field map into a ``kmsv1`` token."""
    data = json.dumps({"fields": fields}, separators=(",", ":"))
    return crypto.encrypt(
        data,
        context=crypto.vault_context(user_id, secret_id),
        key_env=crypto.VAULT_KEY_ENV,
    )


def open_payload(user_id: str, item: dict[str, Any]) -> dict[str, str]:
    """Decrypt a stored secret back into its field map."""
    token = item.get("payloadEnc")
    if not token:
        return {}
    raw = crypto.decrypt(
        token,
        context=crypto.vault_context(user_id, item.get("secretId") or "", "payload"),
        key_env=crypto.VAULT_KEY_ENV,
    )
    try:
        parsed = json.loads(raw)
    except ValueError as exc:  # pragma: no cover - corrupt ciphertext
        raise crypto.CryptoError("secret payload is not valid JSON") from exc
    fields = parsed.get("fields") if isinstance(parsed, dict) else None
    if not isinstance(fields, dict):
        return {}
    return {str(key): str(value) for key, value in fields.items()}


def primary_value(payload: dict[str, str], field: str | None = None) -> str | None:
    """Return the requested field, else the conventional primary secret."""
    if field:
        return payload.get(field)
    for key in _PRIMARY_FIELDS:
        if payload.get(key):
            return payload[key]
    for value in payload.values():
        if value:
            return value
    return None


def validate_field_name(value: Any) -> str:
    if not isinstance(value, str) or not _FIELD_RE.match(value):
        raise ValueError(
            "Secret field names start with a letter and use lowercase letters, "
            "numbers or underscores"
        )
    return value


def mask_preview(value: str | None) -> str:
    """A non-reversible hint (last 4 chars only) shown in the UI.

    No leading characters are revealed — for a generic secret the prefix can be
    as sensitive as the rest, and provider keys are identified by their label.
    """
    value = value or ""
    if len(value) < 12:
        # Too short to reveal any character without leaking most of it.
        return "•" * max(len(value), 4)
    return f"••••…{value[-4:]}"


# --- items -------------------------------------------------------------------


def vault_item(
    *,
    secret_id: str,
    user_id: str,
    name: str,
    label: str,
    description: str,
    kind: str,
    provider: str,
    base_url: str,
    default_model: str,
    payload_enc: str,
    fields: list[str],
    preview: str,
    models: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "pk": user_pk(user_id),
        "sk": vault_sk(name),
        "entity": "vaultSecret",
        "secretId": secret_id,
        "userId": user_id,
        "name": name,
        "label": label,
        "description": description,
        "kind": kind,
        "provider": provider,
        "baseUrl": base_url,
        "defaultModel": default_model,
        "models": list(models or []),
        "payloadEnc": payload_enc,
        "fields": fields,
        "preview": preview,
        "usageCount": 0,
        "lastUsedAt": None,
        "lastTestedAt": None,
        "lastTestStatus": "",
        "lastTestMessage": "",
        "lastTestLatencyMs": None,
        "lastTestModels": [],
        "createdAt": created_at or timestamp,
        "updatedAt": timestamp,
        GSI1[0]: f"VAULT#{secret_id}",
        GSI1[1]: META,
    }


def create_secret(item: dict[str, Any]) -> dict[str, Any]:
    try:
        table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    except Exception as exc:  # noqa: BLE001
        if is_conditional_failure(exc):
            raise DuplicateVaultSecret(item.get("name")) from exc
        raise
    return item


def get_secret(user_id: str, secret_id: str) -> dict[str, Any] | None:
    response = table().query(
        IndexName="byId",
        KeyConditionExpression=f"{GSI1[0]} = :pk",
        ExpressionAttributeValues={":pk": f"VAULT#{secret_id}"},
        Limit=1,
    )
    items = response.get("Items") or []
    if not items:
        return None
    item = items[0]
    if item.get("userId") != user_id:
        return None
    return item


def get_secret_by_name(user_id: str, name: str) -> dict[str, Any] | None:
    response = table().get_item(Key={"pk": user_pk(user_id), "sk": vault_sk(name)})
    return response.get("Item")


def list_secrets(user_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": user_pk(user_id),
            ":prefix": VAULT_PREFIX,
        },
    }
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return sorted(items, key=lambda item: str(item.get("name", "")))


def update_secret(user_id: str, item: dict[str, Any]) -> dict[str, Any] | None:
    """Full replace. Renaming moves the item (name is part of the key)."""
    existing = get_secret(user_id, item["secretId"])
    if existing is None:
        return None
    renamed = existing["sk"] != item["sk"]
    if renamed:
        table().delete_item(Key={"pk": existing["pk"], "sk": existing["sk"]})
    item["createdAt"] = existing.get("createdAt") or item.get("createdAt")
    item["usageCount"] = int(existing.get("usageCount") or 0)
    item["lastUsedAt"] = existing.get("lastUsedAt")
    item["runCount"] = int(existing.get("runCount") or 0)
    item["tokensIn"] = int(existing.get("tokensIn") or 0)
    item["tokensOut"] = int(existing.get("tokensOut") or 0)
    item["tokensTotal"] = int(existing.get("tokensTotal") or 0)
    for key in (
        "lastModel",
        "lastTestedAt",
        "lastTestStatus",
        "lastTestMessage",
        "lastTestLatencyMs",
        "lastTestModels",
    ):
        if key in existing:
            item[key] = existing[key]
    try:
        if renamed:
            # The delete above frees the new key; guard against a racing create.
            table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
        else:
            # Same key: overwrite in place (the item already exists).
            table().put_item(Item=item)
    except Exception as exc:  # noqa: BLE001
        if is_conditional_failure(exc):
            raise DuplicateVaultSecret(item.get("name")) from exc
        raise
    return item


def delete_secret(user_id: str, secret_id: str) -> dict[str, Any] | None:
    existing = get_secret(user_id, secret_id)
    if existing is None:
        return None
    table().delete_item(Key={"pk": existing["pk"], "sk": existing["sk"]})
    return existing


def count_secrets(user_id: str) -> int:
    response = table().query(
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={
            ":pk": user_pk(user_id),
            ":prefix": VAULT_PREFIX,
        },
        Select="COUNT",
    )
    return int(response.get("Count") or 0)


def record_usage(user_id: str, secret_id: str) -> None:
    """Atomically bump a secret's usage counter (best-effort at call sites)."""
    item = get_secret(user_id, secret_id)
    if item is None:
        return
    table().update_item(
        Key={"pk": item["pk"], "sk": item["sk"]},
        UpdateExpression="ADD usageCount :one SET lastUsedAt = :now, updatedAt = :now",
        ExpressionAttributeValues={":one": 1, ":now": now_iso()},
    )


def record_run(
    user_id: str,
    secret_id: str,
    *,
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
) -> None:
    """Record one model run billed through this provider secret.

    Called by the agent runtime when the agent's model is a Vault provider, so
    the Vault (and the Usage page) can show per-service token totals.
    """
    item = get_secret(user_id, secret_id)
    if item is None:
        return
    table().update_item(
        Key={"pk": item["pk"], "sk": item["sk"]},
        UpdateExpression=(
            "ADD runCount :one, tokensIn :tin, tokensOut :tout, tokensTotal :ttot "
            "SET lastModel = :model, lastUsedAt = :now, updatedAt = :now"
        ),
        ExpressionAttributeValues={
            ":one": 1,
            ":tin": max(0, int(input_tokens or 0)),
            ":tout": max(0, int(output_tokens or 0)),
            ":ttot": max(0, int(total_tokens or 0)),
            ":model": str(model or "")[:120],
            ":now": now_iso(),
        },
    )


def record_test(
    user_id: str,
    secret_id: str,
    *,
    ok: bool,
    message: str,
    latency_ms: int | None,
    models: list[str] | None = None,
) -> None:
    item = get_secret(user_id, secret_id)
    if item is None:
        return
    table().update_item(
        Key={"pk": item["pk"], "sk": item["sk"]},
        UpdateExpression=(
            "SET lastTestedAt = :now, lastTestStatus = :status, "
            "lastTestMessage = :message, lastTestLatencyMs = :latency, "
            "lastTestModels = :models, updatedAt = :now"
        ),
        ExpressionAttributeValues={
            ":now": now_iso(),
            ":status": "ok" if ok else "error",
            ":message": message[:500],
            ":latency": latency_ms,
            ":models": list(models or [])[:50],
        },
    )


# --- reference resolution ----------------------------------------------------


def has_references(value: str | None) -> bool:
    """Cheap check before paying for a decrypt."""
    return bool(value) and "{{" in value and "vault:" in value


def resolve_references(user_id: str, value: str, *, default_field: str | None = None) -> str:
    """Replace every ``{{vault:name}}`` / ``{{vault:name.field}}`` in ``value``.

    Used anywhere a stored artifact may reference a secret (MCP API keys,
    provider config, …). Usage is recorded best-effort so a counter write can
    never break a call.
    """
    if not has_references(value):
        return value

    def _replace(match: re.Match[str]) -> str:
        name, field = match.group(1), match.group(2) or default_field
        item = get_secret_by_name(user_id, name)
        if item is None:
            raise VaultReferenceError(f"Vault secret '{name}' was not found")
        payload = open_payload(user_id, item)
        secret = primary_value(payload, field)
        if not secret:
            label = f" field '{field}'" if field else ""
            raise VaultReferenceError(f"Vault secret '{name}'{label} is empty")
        try:
            record_usage(user_id, item.get("secretId") or "")
        except Exception:  # noqa: BLE001 - never fail a call over a counter
            pass
        return secret

    return _REF_RE.sub(_replace, value)
