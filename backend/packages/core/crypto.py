"""KMS-backed field encryption for per-user secrets.

OAuth access/refresh tokens, client secrets and Vault secrets are small, so
this module uses KMS ``Encrypt``/``Decrypt`` directly (rather than envelope
encryption) with an encryption context bound to the owning entity. The context
makes a ciphertext unusable anywhere else, even with the same key.

Two independent callers use this module, each with its own KMS key and its own
context shape so a ciphertext can never be replayed across them:

* MCP connections — ``MCP_CONNECTIONS_KMS_KEY_ARN`` + :func:`connection_context`
* Vault secrets   — ``VAULT_KMS_KEY_ARN`` + :func:`vault_context`

KMS caps direct plaintext at 4096 bytes. These values are well under that; if
one ever grows, switch to envelope encryption (``GenerateDataKey`` + AES-GCM) —
the wire format here is versioned so callers do not change.
"""

from __future__ import annotations

import base64
import os
from typing import Any

# Prefix on every ciphertext so the format can evolve without ambiguity.
_FORMAT = "kmsv1"

# KMS direct-encrypt plaintext ceiling (bytes).
KMS_PLAINTEXT_LIMIT = 4096

# Environment variables holding the key ARN for each caller. The Vault falls
# back to the MCP key when its own is unset so local/dev stacks keep working.
DEFAULT_KEY_ENV = "MCP_CONNECTIONS_KMS_KEY_ARN"
VAULT_KEY_ENV = "VAULT_KMS_KEY_ARN"


class CryptoError(Exception):
    """Credentials could not be encrypted or decrypted."""


def _client() -> Any:
    import boto3

    kwargs: dict[str, Any] = {
        "region_name": os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
    }
    endpoint = os.environ.get("KMS_ENDPOINT_URL") or os.environ.get("AWS_ENDPOINT_URL")
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("kms", **kwargs)


def key_id(env_var: str = DEFAULT_KEY_ENV) -> str:
    value = os.environ.get(env_var)
    if not value and env_var == VAULT_KEY_ENV:
        # Local/dev fallback: reuse the MCP key when no dedicated one is set.
        value = os.environ.get(DEFAULT_KEY_ENV)
    if not value:
        raise CryptoError(f"{env_var} is not set")
    return value


def encrypt(
    plaintext: str | bytes,
    *,
    context: dict[str, str] | None = None,
    key_env: str = DEFAULT_KEY_ENV,
) -> str:
    """Encrypt a secret; returns a base64 ``kmsv1`` token."""
    data = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
    if len(data) > KMS_PLAINTEXT_LIMIT:
        raise CryptoError("secret exceeds the KMS direct-encrypt limit")
    response = _client().encrypt(
        KeyId=key_id(key_env),
        Plaintext=data,
        EncryptionContext=context or {},
    )
    return f"{_FORMAT}:{base64.b64encode(response['CiphertextBlob']).decode('ascii')}"


def decrypt(
    token: str,
    *,
    context: dict[str, str] | None = None,
    key_env: str = DEFAULT_KEY_ENV,
) -> str:
    """Decrypt a ``kmsv1`` token produced by :func:`encrypt`."""
    if not token or not token.startswith(f"{_FORMAT}:"):
        raise CryptoError("unrecognised ciphertext format")
    try:
        blob = base64.b64decode(token.split(":", 1)[1])
    except (ValueError, TypeError) as exc:
        raise CryptoError("ciphertext is not valid base64") from exc
    try:
        response = _client().decrypt(
            CiphertextBlob=blob, EncryptionContext=context or {}
        )
    except Exception as exc:  # noqa: BLE001 - botocore ClientError
        raise CryptoError("could not decrypt secret") from exc
    return response["Plaintext"].decode("utf-8")


def connection_context(user_id: str, conn_id: str, field: str) -> dict[str, str]:
    """Encryption context binding a secret to its owner, connection and field."""
    return {"userId": user_id, "connId": conn_id, "field": field}


def vault_context(user_id: str, secret_id: str, field: str = "payload") -> dict[str, str]:
    """Encryption context binding a Vault secret to its owner and secret id.

    The context keys deliberately differ from :func:`connection_context` so a
    ciphertext produced for one caller is unusable for the other.
    """
    return {"userId": user_id, "secretId": secret_id, "field": field}
