"""DPDP data-rights routes: consent, export, erasure and grievances."""

from __future__ import annotations

import json

from data.client import table
from data.keys import storage_sk, user_pk, vault_sk
from data.repositories.users import get_user_by_sub, list_user_items
from support import load_module, patch_lambda_storage

user_api = load_module(
    "backend/services/apis/user-api/handler.py", "user_api_privacy_handler"
)

CLAIMS = {
    "sub": "auth0|privacy-user",
    "https://get1agent.com/email": "privacy@example.com",
    "https://get1agent.com/name": "Privacy",
}


def _event(method: str, path: str, body=None, query=None) -> dict:
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {"jwt": {"claims": dict(CLAIMS)}},
        },
        "headers": {"x-active-view": "user"},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    if query:
        event["rawQueryString"] = "&".join(f"{k}={v}" for k, v in query.items())
    return event


def _call(method: str, path: str, body=None, query=None, expect: int = 200) -> dict:
    response = user_api.lambda_handler(_event(method, path, body, query), None)
    assert response["statusCode"] == expect, (method, path, response["statusCode"], response["body"])
    return json.loads(response["body"])


def _user_id() -> str:
    return _call("GET", "/v1/user/settings")["id"]


def test_consent_lifecycle(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, user_api, fake_storage)

    info = _call("GET", "/v1/user/consent")
    assert info["consent"] is None
    assert info["contact"]["responseDays"] == 90
    assert any(p["id"] == "account" and p["required"] for p in info["purposes"])

    # Adulthood must be confirmed...
    _call(
        "POST",
        "/v1/user/consent",
        {"purposes": ["account", "service", "ai_processing"]},
        expect=400,
    )
    # ...and every required purpose must be accepted.
    _call(
        "POST",
        "/v1/user/consent",
        {"adultConfirmed": True, "purposes": ["account"]},
        expect=400,
    )

    recorded = _call(
        "POST",
        "/v1/user/consent",
        {
            "adultConfirmed": True,
            "purposes": ["account", "service", "ai_processing", "product_analytics"],
        },
    )
    assert recorded["consent"]["adultConfirmed"] is True
    assert "product_analytics" in recorded["consent"]["purposes"]
    assert recorded["consent"]["consentVersion"]

    fetched = _call("GET", "/v1/user/consent")
    assert fetched["consent"]["acceptedAt"]

    withdrawn = _call("DELETE", "/v1/user/consent")
    assert withdrawn["action"] == "delete_account"
    assert withdrawn["consent"]["withdrawnAt"]


def test_export_includes_data_and_redacts_secrets(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, user_api, fake_storage)
    user_id = _user_id()

    _call("POST", "/v1/knowledge-bases", {"name": "export-kb", "description": "x"}, expect=201)

    # A storage file with bytes behind it, and a Vault secret with ciphertext.
    fake_storage.put_bytes(f"storage/{user_id}/f1/notes.txt", b"hello")
    table().put_item(
        Item={
            "pk": user_pk(user_id),
            "sk": storage_sk("f1"),
            "entity": "storageFile",
            "fileId": "f1",
            "fileName": "notes.txt",
            "size": 5,
            "s3Key": f"storage/{user_id}/f1/notes.txt",
        }
    )
    table().put_item(
        Item={
            "pk": user_pk(user_id),
            "sk": vault_sk("openai"),
            "entity": "vaultSecret",
            "secretId": "s1",
            "name": "openai",
            "secretType": "provider",
            "payloadEnc": "CIPHERTEXT-MUST-NOT-LEAK",
        }
    )

    bundle = _call("GET", "/v1/user/export")
    assert bundle["account"]["email"] == "privacy@example.com"
    assert [kb["name"] for kb in bundle["knowledgeBases"]] == ["export-kb"]
    assert bundle["storageFiles"][0]["fileName"] == "notes.txt"
    assert bundle["storageFiles"][0]["downloadUrl"].startswith("https://s3.test/")
    # The encrypted payload never appears in the export.
    vault = bundle["vaultSecrets"][0]
    assert vault["name"] == "openai"
    assert "payloadEnc" not in vault
    assert "CIPHERTEXT-MUST-NOT-LEAK" not in json.dumps(bundle)
    # Internal keys are never exported.
    assert "pk" not in bundle["account"] and "sk" not in bundle["account"]


def test_account_deletion_erases_everything(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, user_api, fake_storage)
    user_id = _user_id()

    _call("POST", "/v1/knowledge-bases", {"name": "doomed", "description": "x"}, expect=201)

    # S3 artifacts across several prefixes.
    fake_storage.put_bytes(f"raw/{user_id}/kb/doc/file.txt", b"a")
    fake_storage.put_bytes(f"index/{user_id}/vectors.json", b"[]")
    fake_storage.put_bytes(f"conversations/{user_id}/1.json", b"{}")
    fake_storage.put_bytes(f"agent-sessions/{user_id}/agent/session.json", b"{}")

    # A per-run eval partition and a support-thread partition (separate pks).
    table().put_item(
        Item={"pk": user_pk(user_id), "sk": "EVALRUN#r1", "entity": "evalRun", "runId": "r1"}
    )
    table().put_item(
        Item={"pk": "EVALRUN#r1", "sk": "CASE#c1", "entity": "evalCase"}
    )
    table().put_item(
        Item={
            "pk": user_pk(user_id),
            "sk": "SUPPORT#t1",
            "entity": "supportTicket",
            "ticketId": "t1",
            "kind": "support",
        }
    )
    table().put_item(
        Item={"pk": "SUPPORT#t1", "sk": "MSG#x#1", "entity": "supportMessage"}
    )

    result = _call("DELETE", "/v1/user/account")
    assert result["dynamodb"]["userItems"] > 0
    assert result["dynamodb"]["evalRunItems"] == 1
    assert result["dynamodb"]["supportItems"] == 1
    assert result["storageObjects"] >= 4

    # Every trace is gone: partition, identity, child partitions and S3.
    assert list_user_items(user_id) == []
    assert get_user_by_sub(CLAIMS["sub"]) is None
    assert list_user_items("r1") == []
    assert fake_storage.list_keys(f"raw/{user_id}/") == []
    assert fake_storage.list_keys(f"index/{user_id}/") == []
    assert fake_storage.list_keys(f"conversations/{user_id}/") == []
    assert fake_storage.list_keys(f"agent-sessions/{user_id}/") == []

    # A fresh login mints a brand-new account rather than resurrecting data.
    fresh = _user_id()
    assert fresh != user_id


def test_grievance_channel(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, user_api, fake_storage)

    created = _call(
        "POST",
        "/v1/user/grievances",
        {"subject": "Erase my data", "message": "Please erase it", "requestType": "erasure"},
        expect=201,
    )
    assert created["grievance"]["requestType"] == "erasure"
    assert created["contact"]["email"]

    listed = _call("GET", "/v1/user/grievances")
    assert len(listed["grievances"]) == 1

    # Ordinary support tickets are not surfaced as data-rights grievances.
    _call("POST", "/v1/support/messages", {"subject": "Help", "body": "hi"}, expect=201)
    assert len(_call("GET", "/v1/user/grievances")["grievances"]) == 1
