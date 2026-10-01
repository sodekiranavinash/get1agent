"""user-api Playground build-session routes: create/list/detail/turn/rename/delete."""

from __future__ import annotations

import json

from support import load_module, patch_lambda_storage

handler = load_module("backend/services/user-api/handler.py", "user_api_handler_pg")

SUB = "auth0|pgtest"


def _event(method: str, path: str, body=None, query=None) -> dict:
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": SUB,
                        "https://get1agent.com/email": "pg@example.com",
                        "https://get1agent.com/name": "PG",
                    }
                }
            },
        },
        "headers": {"x-active-view": "user"},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    if query:
        event["rawQueryString"] = "&".join(f"{k}={v}" for k, v in query.items())
    return event


def _call(method, path, body=None, query=None, expect=200):
    response = handler.lambda_handler(_event(method, path, body, query), None)
    assert response["statusCode"] == expect, (
        method,
        path,
        response["statusCode"],
        response["body"],
    )
    return json.loads(response["body"])


def _make_tool() -> tuple[str, str]:
    server = _call("POST", "/v1/custom-tools", {"name": "weather-tools"}, expect=201)
    tool = _call(
        "POST",
        f"/v1/custom-tools/{server['id']}/tools",
        {
            "name": "convert-temperature",
            "description": "Convert a temperature.",
            "code": "def run(args):\n    return args\n",
            "inputSchema": {"type": "object", "properties": {}},
            "outputSchema": {"type": "object", "properties": {}},
        },
        expect=201,
    )
    return server["id"], tool["id"]


def test_playground_session_lifecycle(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    server_id, tool_id = _make_tool()

    created = _call(
        "POST",
        "/v1/custom-tools/sessions",
        {"serverId": server_id, "toolId": tool_id},
        expect=201,
    )
    session_id = created["id"]
    assert created["serverId"] == server_id
    assert created["toolId"] == tool_id
    assert created["messages"] == []

    # A canned generator stand-in (no network / model call).
    monkeypatch.setattr(
        handler,
        "generate_tool",
        lambda description, **kwargs: {
            "name": "convert-temperature",
            "description": description,
            "code": "def run(args):\n    return {'ok': True}\n",
            "inputSchema": {"type": "object", "properties": {}},
            "outputSchema": {"type": "object", "properties": {}},
        },
    )
    # Capture the background job instead of invoking Lambda for real.
    job: dict = {}
    monkeypatch.setattr(handler, "_invoke_self_async", lambda payload: job.update(payload))

    turn = _call(
        "POST",
        f"/v1/custom-tools/sessions/{session_id}/turn",
        {"prompt": "make it return ok", "code": "def run(args):\n    return args\n"},
    )
    assert turn["messages"][0]["role"] == "user"
    placeholder = turn["messages"][1]
    assert placeholder["role"] == "assistant" and placeholder["status"] == "generating"

    # The background worker resolves the placeholder out of band.
    assert job.get(handler._ASYNC_ACTION) == "playground.generate"
    handler._run_playground_generate_job(job)

    resolved = _call("GET", f"/v1/custom-tools/sessions/{session_id}")
    assistant = resolved["messages"][-1]
    assert assistant["role"] == "assistant" and assistant["status"] == "ok"
    assert assistant["generated"]["code"].startswith("def run")
    assert assistant["baseCode"] == "def run(args):\n    return args\n"

    # The metadata item stays small; the transcript (with both messages) is S3.
    user_id = _call("GET", "/v1/user/settings")["id"]
    from retrieval.layout import playground_key

    key = playground_key(user_id, session_id)
    assert key in fake_storage.data
    assert len(fake_storage.get_json(key)["messages"]) == 2

    detail = _call("GET", f"/v1/custom-tools/sessions/{session_id}")
    assert len(detail["messages"]) == 2
    assert detail["messageCount"] == 2
    assert detail["title"]  # first prompt seeds the title

    listing = _call("GET", "/v1/custom-tools/sessions")
    assert [item["id"] for item in listing["sessions"]] == [session_id]

    filtered = _call("GET", "/v1/custom-tools/sessions", query={"toolId": tool_id})
    assert [item["id"] for item in filtered["sessions"]] == [session_id]
    missing = _call(
        "GET", "/v1/custom-tools/sessions", query={"toolId": "0" * 36}
    )
    assert missing["sessions"] == []

    renamed = _call(
        "PATCH", f"/v1/custom-tools/sessions/{session_id}", {"title": "Weather"}
    )
    assert renamed["title"] == "Weather"

    _call("DELETE", f"/v1/custom-tools/sessions/{session_id}")
    _call("GET", f"/v1/custom-tools/sessions/{session_id}", expect=404)
    assert key not in fake_storage.data


def test_playground_session_binding_is_owned(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    _call("GET", "/v1/user/settings")  # provision the user
    missing = "00000000-0000-0000-0000-000000000000"
    _call(
        "POST",
        "/v1/custom-tools/sessions",
        {"toolId": missing},
        expect=404,
    )
    _call(
        "POST",
        "/v1/custom-tools/sessions",
        {"serverId": missing},
        expect=404,
    )


def test_playground_turn_requires_prompt(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    created = _call("POST", "/v1/custom-tools/sessions", {}, expect=201)
    _call(
        "POST",
        f"/v1/custom-tools/sessions/{created['id']}/turn",
        {"prompt": "  "},
        expect=400,
    )
