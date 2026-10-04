"""Unit tests for the AgentCore Identity helper (no AWS calls)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages"))

from core import identity  # noqa: E402

_ENV = {
    "AGENT_WORKLOAD_IDENTITY_ARN": "arn:aws:bedrock-agentcore:ap-south-1:1:workload-identity/agent-1",
    "AGENT_TOKEN_VAULT_ID": "vault-1",
    "AGENT_IDENTITY_PROVIDERS": (
        "arn:aws:bedrock-agentcore:ap-south-1:1:credential-provider/google-provider/abc,"
        "arn:aws:bedrock-agentcore:ap-south-1:1:credential-provider/github-provider/def"
    ),
}


def _clear(monkeypatch) -> None:
    for name in (
        "AGENT_WORKLOAD_IDENTITY_ARN",
        "AGENT_TOKEN_VAULT_ID",
        "AGENT_IDENTITY_PROVIDERS",
        "AGENT_IDENTITY_RETURN_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_disabled_without_config(monkeypatch) -> None:
    _clear(monkeypatch)
    assert identity.enabled() is False
    assert identity.describe()["configured"] is False
    with mock.patch.dict(os.environ, {}, clear=False):
        try:
            identity.get_token("u_1", "github")
            raise AssertionError("expected RuntimeError")
        except RuntimeError:
            pass


def test_provider_resolution(monkeypatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("AGENT_IDENTITY_PROVIDERS", _ENV["AGENT_IDENTITY_PROVIDERS"])
    assert identity.provider_for("github").endswith("github-provider/def")
    assert identity.provider_for("nope") is None


def test_get_token_calls_agentcore(monkeypatch) -> None:
    _clear(monkeypatch)
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)

    class _Client:
        def __init__(self):
            self.calls = []

        def get_resource_oauth2_token(self, **kwargs):
            self.calls.append(kwargs)
            return {"accessToken": "t", "expiresAt": "2026-01-01T00:00:00Z"}

    client = _Client()
    with mock.patch.object(identity, "_client", lambda: client):
        token = identity.get_token("u_1", "github", scopes=["repo"])

    assert token["accessToken"] == "t"
    call = client.calls[0]
    assert call["userId"] == "u_1"
    assert call["credentialProviderArn"].endswith("github-provider/def")
    assert call["scopes"] == ["repo"]
    assert identity.enabled() is True


def test_describe_lists_providers(monkeypatch) -> None:
    _clear(monkeypatch)
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)
    described = identity.describe()
    assert described["configured"] is True
    assert len(described["providers"]) == 2
    assert described["tokenVaultId"] == "vault-1"


if __name__ == "__main__":
    unittest.main()
