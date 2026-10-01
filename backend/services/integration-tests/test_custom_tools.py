"""Custom-tools (Playground) coverage: server/tool CRUD + generate/test routes."""

from __future__ import annotations

import json

from support import load_module, patch_lambda_storage

handler = load_module("backend/services/user-api/handler.py", "user_api_custom_tools")

SUB = "auth0|customtools"

TOOL_CODE = "def run(args):\n    return {'echo': args}\n"


def _event(method: str, path: str, body=None, view: str = "user") -> dict:
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": SUB,
                        "https://get1agent.com/email": "custom@example.com",
                        "https://get1agent.com/name": "Custom",
                    }
                }
            },
        },
        "headers": {"x-active-view": view},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _call(method, path, body=None, expect=200, view="user"):
    response = handler.lambda_handler(_event(method, path, body, view), None)
    assert response["statusCode"] == expect, (method, path, response["statusCode"], response["body"])
    return json.loads(response["body"])


def _tool_payload(name: str = "echo") -> dict:
    return {
        "name": name,
        "description": "Echo the arguments back.",
        "code": TOOL_CODE,
        "inputSchema": {"type": "object", "properties": {"value": {"type": "string"}}},
        "outputSchema": {"type": "object", "properties": {"echo": {"type": "object"}}},
    }


def test_server_and_tool_crud(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)

    created = _call("POST", "/v1/custom-tools", {"name": "my-tools", "description": "hi"}, expect=201)
    server_id = created["id"]
    assert created["slug"] == "my-tools" and created["tools"] == []
    _call("POST", "/v1/custom-tools", {"name": "my-tools"}, expect=409)

    listed = _call("GET", "/v1/custom-tools")
    assert listed["servers"][0]["slug"] == "my-tools"
    assert listed["usage"]["limits"]["servers"] == 20

    tool = _call("POST", f"/v1/custom-tools/{server_id}/tools", _tool_payload(), expect=201)
    tool_id = tool["id"]
    assert tool["code"] == TOOL_CODE
    _call("POST", f"/v1/custom-tools/{server_id}/tools", _tool_payload(), expect=409)

    detail = _call("GET", f"/v1/custom-tools/{server_id}")
    assert detail["toolCount"] == 1
    assert detail["tools"][0]["code"] == TOOL_CODE

    updated = _call(
        "PUT",
        f"/v1/custom-tools/{server_id}/tools/{tool_id}",
        {**_tool_payload(), "description": "Updated."},
    )
    assert updated["description"] == "Updated."

    # The source is stored in S3 under the custom/ prefix.
    assert any(key.startswith("custom/") for key in fake_storage.data)

    _call("DELETE", f"/v1/custom-tools/{server_id}/tools/{tool_id}")
    assert _call("GET", f"/v1/custom-tools/{server_id}")["toolCount"] == 0

    _call("DELETE", f"/v1/custom-tools/{server_id}")
    assert _call("GET", "/v1/custom-tools")["servers"] == []


def test_invalid_names_are_rejected(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    _call("POST", "/v1/custom-tools", {"name": "Bad Name!"}, expect=400)

    server = _call("POST", "/v1/custom-tools", {"name": "valid-name"}, expect=201)
    _call(
        "POST",
        f"/v1/custom-tools/{server['id']}/tools",
        {**_tool_payload("Bad Tool!"), "name": "Bad Tool!"},
        expect=400,
    )


def test_test_route_invokes_runner(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    captured: dict = {}

    def fake_invoke(payload):
        captured.update(payload)
        return {"ok": True, "result": {"echo": payload["args"]}, "durationMs": 5}

    monkeypatch.setattr(handler, "_invoke_custom_tools", fake_invoke)

    result = _call(
        "POST",
        "/v1/custom-tools/test",
        {
            "code": TOOL_CODE,
            "args": {"value": "hi"},
            "inputSchema": {"type": "object"},
            "outputSchema": {"type": "object"},
        },
    )
    assert result["ok"] is True
    assert result["result"] == {"echo": {"value": "hi"}}
    assert captured["action"] == "test"
    assert captured["code"] == TOOL_CODE


def test_generate_route_uses_generator(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    generated = {
        "name": "temperature",
        "description": "Convert temperatures.",
        "code": "def run(args):\n    return {'c': 0}\n",
        "inputSchema": {"type": "object", "properties": {}},
        "outputSchema": {"type": "object", "properties": {}},
    }
    monkeypatch.setattr(handler, "generate_tool", lambda *a, **k: generated)

    result = _call("POST", "/v1/custom-tools/generate", {"description": "convert temperature"})
    assert result["name"] == "temperature"
    assert result["code"].startswith("def run")
