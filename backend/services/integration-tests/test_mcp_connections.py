"""MCP connections repository + KMS-backed credential storage.

Uses the moto-backed DynamoDB table and moto KMS from ``conftest``.
"""

from __future__ import annotations

import os

import boto3
import pytest

from core import crypto
from data.repositories import mcp_connections as repo

USER = "u_7k3f9qz2mpx8n4rq"
CONN = "11111111-1111-1111-1111-111111111111"


def _make_connection() -> dict:
    return repo.create_connection(
        USER,
        CONN,
        name="github",
        server_url="https://api.githubcopilot.com/mcp/",
        auth_type="oauth",
        scopes=["repo"],
    )


def test_create_get_list_delete() -> None:
    _make_connection()
    assert repo.get_connection(USER, CONN)["name"] == "github"
    assert [c["connId"] for c in repo.list_connections(USER)] == [CONN]
    assert repo.count_connections(USER) == 1

    removed = repo.delete_connection(USER, CONN)
    assert removed is not None
    assert repo.get_connection(USER, CONN) is None
    assert repo.list_connections(USER) == []


def test_duplicate_connection_key_fails() -> None:
    _make_connection()
    with pytest.raises(Exception):
        _make_connection()


def test_update_and_status_clears_error() -> None:
    _make_connection()
    repo.set_status(USER, CONN, repo.STATUS_ERROR, error="boom")
    assert repo.get_connection(USER, CONN)["lastError"] == "boom"

    repo.set_status(USER, CONN, repo.STATUS_CONNECTED, tool_count=7)
    item = repo.get_connection(USER, CONN)
    assert item["status"] == repo.STATUS_CONNECTED
    assert item["toolCount"] == 7
    assert "lastError" not in item


def test_enabled_defaults_true_and_toggles() -> None:
    _make_connection()
    assert repo.get_connection(USER, CONN)["enabled"] is True

    repo.set_enabled(USER, CONN, False)
    assert repo.get_connection(USER, CONN)["enabled"] is False

    repo.set_enabled(USER, CONN, True)
    assert repo.get_connection(USER, CONN)["enabled"] is True


def test_tool_enabled_toggles_and_is_idempotent() -> None:
    _make_connection()
    assert repo.get_connection(USER, CONN)["disabledTools"] == []

    repo.set_tool_enabled(USER, CONN, "search", False)
    repo.set_tool_enabled(USER, CONN, "search", False)
    assert repo.get_connection(USER, CONN)["disabledTools"] == ["search"]

    repo.set_tool_enabled(USER, CONN, "search", True)
    assert repo.get_connection(USER, CONN)["disabledTools"] == []


def test_description_is_stored() -> None:
    repo.create_connection(
        USER,
        "22222222-2222-2222-2222-222222222222",
        name="custom",
        server_url="https://custom.example.com/mcp",
        auth_type="none",
        description="Does custom things",
    )
    item = repo.get_connection(USER, "22222222-2222-2222-2222-222222222222")
    assert item["description"] == "Does custom things"


def test_refresh_rotation_is_compare_and_swap() -> None:
    _make_connection()
    repo.save_tokens(USER, CONN, access_token_enc="a1", refresh_token_enc="r1")

    # A second writer still holding r1 loses the race.
    with pytest.raises(repo.RefreshConflict):
        repo.save_tokens(
            USER, CONN, access_token_enc="a2", refresh_token_enc="r2", expected_refresh_enc="stale"
        )

    # The current holder rotates successfully.
    repo.save_tokens(
        USER, CONN, access_token_enc="a2", refresh_token_enc="r2", expected_refresh_enc="r1"
    )
    item = repo.get_connection(USER, CONN)
    assert item["accessTokenEnc"] == "a2"
    assert item["refreshTokenEnc"] == "r2"


def test_state_is_single_use() -> None:
    repo.create_state(USER, "u_x.abc", connId=CONN, codeVerifier="v")
    first = repo.consume_state(USER, "u_x.abc")
    assert first is not None and first["codeVerifier"] == "v"
    assert repo.consume_state(USER, "u_x.abc") is None


def test_kms_round_trip_and_context_binding() -> None:
    key = boto3.client("kms", region_name="us-east-1").create_key(Description="test")["KeyMetadata"]
    os.environ["MCP_CONNECTIONS_KMS_KEY_ARN"] = key["Arn"]
    try:
        context = crypto.connection_context(USER, CONN, "refreshToken")
        token = crypto.encrypt("super-secret", context=context)
        assert token.startswith("kmsv1:")
        assert crypto.decrypt(token, context=context) == "super-secret"

        # A different encryption context must not decrypt.
        with pytest.raises(crypto.CryptoError):
            crypto.decrypt(token, context=crypto.connection_context(USER, "other", "refreshToken"))
    finally:
        os.environ.pop("MCP_CONNECTIONS_KMS_KEY_ARN", None)
