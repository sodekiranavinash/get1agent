"""The ``auto`` model sentinel: API validation for agents and workflows."""

from __future__ import annotations

import pytest

from support import load_module

handler = load_module("backend/services/apis/user-api/handler.py", "user_api_handler_routing")


def test_agent_accepts_auto_on_the_platform() -> None:
    config = handler._validated_agent_config(
        {"prompt": "You are a helpful assistant used only in tests.", "model": "auto"}
    )
    assert config["model"] == "auto"
    assert config["providerSecretId"] == ""


def test_agent_rejects_auto_with_a_provider() -> None:
    with pytest.raises(handler.ApiError):
        handler._validated_agent_config(
            {
                "prompt": "You are a helpful assistant used only in tests.",
                "providerSecretId": "3c9a1f2e-1b2c-4d5e-8f90-1234567890ab",
                "model": "auto",
            }
        )


def test_workflow_host_and_override_accept_auto() -> None:
    overrides = handler._validated_workflow_overrides({"model": "auto"})
    assert overrides["model"] == "auto"

    data = handler._validated_workflow_node_data("input", {"model": "auto"})
    assert data["model"] == "auto"


def test_agent_still_rejects_unknown_models() -> None:
    with pytest.raises(handler.ApiError):
        handler._validated_agent_config(
            {"prompt": "You are a helpful assistant used only in tests.", "model": "nope"}
        )
