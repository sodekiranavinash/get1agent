"""AgentCore Identity helper (managed OAuth token vault + on-behalf-of access).

When a tool (or a remote MCP server) needs a user's third-party token, the
platform asks **AgentCore Identity** for it instead of storing the token itself:
the workload identity is the runtime's machine identity, the user is the
resource owner, and the token is returned on demand.

Best-effort by design — every helper degrades to "not configured" so a missing
Identity setup never breaks a run.

Config: ``AGENT_WORKLOAD_IDENTITY_ARN``, ``AGENT_TOKEN_VAULT_ID``,
``AGENT_IDENTITY_PROVIDERS`` (comma-separated provider ARNs), ``BEDROCK_REGION``.
"""

from __future__ import annotations

import os
from typing import Any


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def workload_identity_arn() -> str:
    return _env("AGENT_WORKLOAD_IDENTITY_ARN")


def token_vault_id() -> str:
    return _env("AGENT_TOKEN_VAULT_ID")


def provider_arns() -> list[str]:
    raw = _env("AGENT_IDENTITY_PROVIDERS")
    return [part.strip() for part in raw.split(",") if part.strip()]


def region() -> str:
    return _env("BEDROCK_REGION") or _env("AWS_REGION") or "ap-south-1"


def enabled() -> bool:
    return bool(workload_identity_arn() and provider_arns())


def _client() -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(
        "bedrock-agentcore",
        region_name=region(),
        config=Config(retries={"max_attempts": 4, "mode": "adaptive"}),
    )


def provider_for(key: str) -> str | None:
    """Resolve a provider key (e.g. ``github``) to its credential provider ARN."""
    needle = (key or "").strip().lower()
    if not needle:
        return None
    for arn in provider_arns():
        if needle in arn.lower():
            return arn
    return None


def get_token(
    user_id: str,
    provider: str,
    *,
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch an OAuth token for ``user_id`` from AgentCore Identity.

    Returns ``{"accessToken", "expiresAt", ...}``. Raises ``RuntimeError`` when
    Identity is not configured or the provider is unknown, so callers can fall
    back to the Vault.
    """
    if not enabled():
        raise RuntimeError("AgentCore Identity is not configured")
    provider_arn = provider_for(provider)
    if not provider_arn:
        raise RuntimeError(f"Unknown identity provider: {provider}")

    kwargs: dict[str, Any] = {
        "workloadIdentityArn": workload_identity_arn(),
        "credentialProviderArn": provider_arn,
        "resourceOauth2ReturnUrl": _env("AGENT_IDENTITY_RETURN_URL")
        or "https://api.get1agent.com/v1/identity/callback",
        "userId": user_id,
    }
    if scopes:
        kwargs["scopes"] = scopes
    return _client().get_resource_oauth2_token(**kwargs)


def describe() -> dict[str, Any]:
    """Status for the API/UI: which providers are wired."""
    return {
        "configured": enabled(),
        "workloadIdentityArn": workload_identity_arn() or None,
        "tokenVaultId": token_vault_id() or None,
        "providers": provider_arns(),
        "region": region(),
    }
