"""Vault: encrypted-secret repository + user-api route coverage."""

from __future__ import annotations

import json
import os

import boto3
import pytest

from data.repositories import vault as repo
from support import load_module, patch_lambda_storage

handler = load_module("backend/services/apis/user-api/handler.py", "user_api_handler_vault")

USER = "u_7k3f9qz2mpx8n4rq"
SUB = "auth0|vaulttest"


@pytest.fixture
def vault_key(_aws):
    """A moto KMS key exposed as the Vault key for the test."""
    arn = boto3.client("kms", region_name="us-east-1").create_key(
        Description="vault-test"
    )["KeyMetadata"]["Arn"]
    os.environ["VAULT_KMS_KEY_ARN"] = arn
    try:
        yield arn
    finally:
        os.environ.pop("VAULT_KMS_KEY_ARN", None)


def _item(secret_id: str, name: str, fields: dict[str, str], **kwargs) -> dict:
    return repo.vault_item(
        secret_id=secret_id,
        user_id=USER,
        name=name,
        label=kwargs.get("label", name),
        description="",
        kind=kwargs.get("kind", "generic"),
        provider=kwargs.get("provider", ""),
        base_url=kwargs.get("base_url", ""),
        default_model="",
        fields=sorted(fields),
        payload_enc=repo.seal_payload(USER, secret_id, fields),
        preview=repo.mask_preview(repo.primary_value(fields)),
    )


# --- repository ---------------------------------------------------------------


def test_create_get_list_delete(vault_key):
    repo.create_secret(_item("s1", "openai-key", {"value": "sk-abcdef1234567890"}))
    got = repo.get_secret(USER, "s1")
    assert got["name"] == "openai-key"
    assert repo.get_secret_by_name(USER, "openai-key")["secretId"] == "s1"
    assert [item["secretId"] for item in repo.list_secrets(USER)] == ["s1"]
    assert repo.open_payload(USER, got) == {"value": "sk-abcdef1234567890"}

    assert repo.delete_secret(USER, "s1") is not None
    assert repo.list_secrets(USER) == []
    assert repo.get_secret(USER, "s1") is None


def test_duplicate_name_is_rejected(vault_key):
    repo.create_secret(_item("s1", "dup", {"value": "x"}))
    with pytest.raises(repo.DuplicateVaultSecret):
        repo.create_secret(_item("s2", "dup", {"value": "y"}))


def test_ciphertext_is_bound_to_its_secret(vault_key):
    from core import crypto

    repo.create_secret(_item("s1", "ctx", {"value": "top-secret"}))
    item = repo.get_secret(USER, "s1")
    assert item["payloadEnc"].startswith("kmsv1:")
    # Same key, wrong context — decryption must fail.
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(
            item["payloadEnc"],
            context=crypto.vault_context(USER, "other"),
            key_env=crypto.VAULT_KEY_ENV,
        )


def test_usage_and_test_counters(vault_key):
    repo.create_secret(_item("s1", "stats", {"value": "v"}))
    repo.record_usage(USER, "s1")
    repo.record_usage(USER, "s1")
    repo.record_test(USER, "s1", ok=True, message="ok", latency_ms=42, models=["a", "b"])
    item = repo.get_secret(USER, "s1")
    assert item["usageCount"] == 2 and item["lastUsedAt"]
    assert item["lastTestStatus"] == "ok"
    assert item["lastTestLatencyMs"] == 42
    assert item["lastTestModels"] == ["a", "b"]


def test_record_run_accumulates_tokens(vault_key):
    repo.create_secret(
        _item(
            "s1",
            "prov",
            {"apiKey": "sk-123456789012"},
            kind="provider",
            provider="openai",
            base_url="https://api.openai.com/v1",
        )
    )
    repo.record_run(USER, "s1", model="gpt-4o-mini", input_tokens=10, output_tokens=5, total_tokens=15)
    repo.record_run(USER, "s1", model="gpt-4o-mini", input_tokens=1, output_tokens=2, total_tokens=3)
    item = repo.get_secret(USER, "s1")
    assert item["runCount"] == 2
    assert item["tokensIn"] == 11
    assert item["tokensOut"] == 7
    assert item["tokensTotal"] == 18
    assert item["lastModel"] == "gpt-4o-mini"


def test_resolve_references(vault_key):
    repo.create_secret(_item("s1", "gh", {"apiKey": "ghp_1234567890abcdef"}))
    repo.create_secret(_item("s2", "multi", {"apiKey": "primary", "region": "eu"}))

    assert repo.has_references("Bearer {{vault:gh}}")
    assert not repo.has_references("Bearer plain")
    assert (
        repo.resolve_references(USER, "Bearer {{vault:gh}}")
        == "Bearer ghp_1234567890abcdef"
    )
    assert repo.resolve_references(USER, "{{ vault:multi.region }}") == "eu"
    assert repo.resolve_references(USER, "no refs here") == "no refs here"
    with pytest.raises(repo.VaultReferenceError):
        repo.resolve_references(USER, "{{vault:missing}}")


# --- routes -------------------------------------------------------------------


def _event(method: str, path: str, body=None) -> dict:
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": SUB,
                        "https://get1agent.com/email": "vault@example.com",
                    }
                }
            },
        },
        "headers": {"x-active-view": "user"},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _call(method: str, path: str, body=None, expect: int = 200):
    response = handler.lambda_handler(_event(method, path, body), None)
    assert response["statusCode"] == expect, (path, response["statusCode"], response["body"])
    return json.loads(response["body"])


def test_vault_routes(fake_storage, monkeypatch, vault_key):
    patch_lambda_storage(monkeypatch, handler, fake_storage)

    providers = _call("GET", "/v1/vault/providers")
    assert any(provider["id"] == "openai" for provider in providers["providers"])

    created = _call(
        "POST",
        "/v1/vault/secrets",
        {
            "name": "openai-prod",
            "label": "OpenAI prod",
            "kind": "provider",
            "provider": "openai",
            "baseUrl": "https://api.openai.com/v1",
            "defaultModel": "gpt-4o-mini",
            "apiKey": "sk-live-1234567890abcdef",
        },
        expect=201,
    )
    assert created["preview"] == "••••…cdef"
    assert "payloadEnc" not in created
    secret_id = created["id"]

    listed = _call("GET", "/v1/vault/secrets")
    assert listed["secrets"][0]["name"] == "openai-prod"
    assert listed["usage"]["providerCount"] == 1
    # Never leak plaintext or ciphertext in a list response.
    body = json.dumps(listed)
    assert "sk-live-1234567890abcdef" not in body
    assert "kmsv1" not in body

    revealed = _call("POST", f"/v1/vault/secrets/{secret_id}/reveal")
    assert revealed["fields"] == {"apiKey": "sk-live-1234567890abcdef"}

    # Updating without re-sending the key keeps the stored one.
    # There is no separate display label: the reference name is the label.
    updated = _call("PUT", f"/v1/vault/secrets/{secret_id}", {"description": "renamed note"})
    assert updated["label"] == "openai-prod"
    assert updated["description"] == "renamed note"
    assert (
        _call("POST", f"/v1/vault/secrets/{secret_id}/reveal")["fields"]["apiKey"]
        == "sk-live-1234567890abcdef"
    )

    _call("POST", "/v1/vault/secrets", {"name": "openai-prod", "apiKey": "x"}, expect=409)

    generic = _call(
        "POST",
        "/v1/vault/secrets",
        {"name": "sentry-dsn", "value": "https://abc@sentry.io/1"},
        expect=201,
    )
    assert generic["kind"] == "generic"

    _call("DELETE", f"/v1/vault/secrets/{secret_id}")
    _call("GET", f"/v1/vault/secrets/{secret_id}", expect=404)


def test_settings_exposes_budget_and_pricing(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    payload = _call("GET", "/v1/user/settings")
    assert payload["budget"]["budgetUsd"] == 0.5
    assert payload["budget"]["budgetCredits"] == 50.0
    assert payload["budget"]["spentUsd"] == 0.0
    assert payload["budget"]["unlimited"] is False
    assert payload["pricing"]["__default__"]["input"] >= 0
    assert "nvidia.nemotron-nano-3-30b" in payload["pricing"]


def test_vault_usage_reports_runs_and_tokens(fake_storage, monkeypatch, vault_key):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    user_id = _call("GET", "/v1/user/settings")["id"]
    created = _call(
        "POST",
        "/v1/vault/secrets",
        {
            "name": "prov",
            "kind": "provider",
            "provider": "openai",
            "baseUrl": "https://api.openai.com/v1",
            "defaultModel": "gpt-4o-mini",
            "apiKey": "sk-123456789012",
        },
        expect=201,
    )
    repo.record_run(
        user_id, created["id"], model="gpt-4o-mini", input_tokens=120, output_tokens=30, total_tokens=150
    )
    listed = _call("GET", "/v1/vault/secrets")
    usage = listed["secrets"][0]["usage"]
    assert usage["runs"] == 1
    assert usage["tokensIn"] == 120
    assert usage["tokensTotal"] == 150
    assert usage["lastModel"] == "gpt-4o-mini"


def test_agent_config_accepts_provider_model(fake_storage, monkeypatch, vault_key):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    created = _call(
        "POST",
        "/v1/vault/secrets",
        {
            "name": "agent-provider",
            "kind": "provider",
            "provider": "openai",
            "apiKey": "sk-123456789012",
        },
        expect=201,
    )
    validated = handler._validated_agent_config(
        {
            "prompt": "You are a helpful assistant used only in tests.",
            "providerSecretId": created["id"],
            "model": "gpt-4o-mini",
        }
    )
    assert validated["providerSecretId"] == created["id"]
    assert validated["model"] == "gpt-4o-mini"

    # Without a provider the model must still be a platform model.
    with pytest.raises(handler.ApiError):
        handler._validated_agent_config(
            {"prompt": "You are a helpful assistant used only in tests.", "model": "nope"}
        )
    platform = handler._validated_agent_config(
        {"prompt": "You are a helpful assistant used only in tests."}
    )
    assert platform["providerSecretId"] == ""
    assert platform["model"] in handler.SUPPORTED_AGENT_MODELS


def test_vault_provider_multiple_models(fake_storage, monkeypatch, vault_key):
    patch_lambda_storage(monkeypatch, handler, fake_storage)

    providers = _call("GET", "/v1/vault/providers")
    openai = next(provider for provider in providers["providers"] if provider["id"] == "openai")
    assert openai["models"] and openai["defaultModel"] in openai["models"]

    created = _call(
        "POST",
        "/v1/vault/secrets",
        {
            "name": "multi",
            "kind": "provider",
            "provider": "openai",
            "baseUrl": "https://api.openai.com/v1",
            "apiKey": "sk-123456789012",
            "models": ["gpt-4o", "gpt-4o-mini", "o4-mini"],
            "defaultModel": "gpt-4o-mini",
        },
        expect=201,
    )
    assert created["models"] == ["gpt-4o", "gpt-4o-mini", "o4-mini"]
    assert created["defaultModel"] == "gpt-4o-mini"

    # A default that is not listed is added so it stays selectable.
    created2 = _call(
        "POST",
        "/v1/vault/secrets",
        {
            "name": "multi2",
            "kind": "provider",
            "provider": "custom",
            "baseUrl": "https://llm.example.com/v1",
            "apiKey": "sk-123456789012",
            "models": ["a"],
            "defaultModel": "b",
        },
        expect=201,
    )
    assert created2["models"] == ["b", "a"]

    # Updating the model list keeps the others; default must remain valid.
    updated = _call(
        "PUT",
        f"/v1/vault/secrets/{created['id']}",
        {"models": ["gpt-4o", "o4-mini"], "defaultModel": "o4-mini"},
    )
    assert updated["models"] == ["gpt-4o", "o4-mini"]
    assert updated["defaultModel"] == "o4-mini"


def test_vault_test_routes(fake_storage, monkeypatch, vault_key):
    patch_lambda_storage(monkeypatch, handler, fake_storage)

    monkeypatch.setattr(
        handler,
        "test_vault_provider",
        lambda **kwargs: {
            "ok": True,
            "provider": kwargs.get("provider_id"),
            "baseUrl": kwargs.get("base_url"),
            "status": 200,
            "latencyMs": 12,
            "models": ["gpt-4o-mini"],
            "model": kwargs.get("model"),
            "sample": "ok",
            "usage": {"total_tokens": 3},
            "message": "Connected",
            "checkedAt": "2026-01-01T00:00:00Z",
        },
    )

    created = _call(
        "POST",
        "/v1/vault/secrets",
        {
            "name": "live",
            "kind": "provider",
            "provider": "openai",
            "apiKey": "sk-x123456789012",
        },
        expect=201,
    )
    result = _call("POST", f"/v1/vault/secrets/{created['id']}/test")
    assert result["ok"] is True and result["latencyMs"] == 12

    listed = _call("GET", "/v1/vault/secrets")
    assert listed["secrets"][0]["test"]["status"] == "ok"
    assert listed["secrets"][0]["test"]["models"] == ["gpt-4o-mini"]

    adhoc = _call(
        "POST",
        "/v1/vault/test",
        {
            "provider": "openai",
            "baseUrl": "https://api.openai.com/v1",
            "apiKey": "sk-x",
            "model": "gpt-4o-mini",
        },
    )
    assert adhoc["ok"] is True
