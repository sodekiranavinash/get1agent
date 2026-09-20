"""user-api conversation routes: create/list/detail/rename/delete + agent runs."""

from __future__ import annotations

import json

from support import load_module, patch_lambda_storage

handler = load_module("backend/services/user-api/handler.py", "user_api_handler_conv")

SUB = "auth0|convtest"


def _event(method: str, path: str, body=None, query=None) -> dict:
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": SUB,
                        "https://get1agent.com/email": "conv@example.com",
                        "https://get1agent.com/name": "Conv",
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
    assert response["statusCode"] == expect, (method, path, response["statusCode"], response["body"])
    return json.loads(response["body"])


def _create_agent() -> dict:
    payload = {
        "name": "chatty",
        "description": "d",
        "config": {
            "version": 2,
            "prompt": "You are helpful.",
            "model": "deepseek-v4-flash-vision-exp",
            "reasoning": "medium",
            "outputFormat": "markdown",
            "input": {"query": "", "fileIds": []},
            "output": {"format": "markdown", "instructions": ""},
            "defaultQuestions": [],
            "knowledgeBaseIds": [],
            "knowledgeRerank": False,
            "skillIds": [],
            "servers": [],
            "memory": {"enabled": False},
            "schedule": {"enabled": False, "cron": "", "timezone": "UTC"},
            "graph": {"nodes": [{"id": "agent-1", "type": "agent"}], "edges": []},
        },
    }
    return _call("POST", "/v1/agents", payload, expect=201)


def test_conversation_lifecycle(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    agent = _create_agent()
    agent_id = agent["id"]
    user_id = _call("GET", "/v1/user/settings")["id"]

    first = _call("POST", "/v1/conversations", {"agentId": agent_id, "title": "Hello"}, expect=201)
    cid = first["conversationId"]
    assert isinstance(cid, int) and cid > 0
    assert first["kind"] == "chat" and first["title"] == "Hello"

    second = _call("POST", "/v1/conversations", {"agentId": agent_id, "kind": "run"}, expect=201)
    # Global sequence: the second conversation gets a strictly larger id.
    assert second["conversationId"] > cid

    listing = _call("GET", "/v1/conversations")
    assert len(listing["conversations"]) == 2

    runs = _call("GET", f"/v1/agents/{agent_id}/runs")
    assert {run["conversationId"] for run in runs["runs"]} == {
        cid,
        second["conversationId"],
    }

    # Seed a transcript the way the runtime does, then read it back.
    from retrieval.layout import conversation_key

    fake_storage.put_json(
        conversation_key(user_id, cid),
        {
            "conversationId": cid,
            "userId": user_id,
            "turns": [
                {
                    "runId": "run-1",
                    "question": "hi",
                    "model": "deepseek-v4-flash-vision-exp",
                    "agentId": agent_id,
                    "agentName": "chatty",
                    "status": "completed",
                    "events": [{"type": "text", "data": "hello"}],
                }
            ],
        },
    )
    detail = _call("GET", f"/v1/conversations/{cid}")
    assert detail["conversation"]["conversationId"] == cid
    assert detail["turns"][0]["runId"] == "run-1"

    renamed = _call("PATCH", f"/v1/conversations/{cid}", {"title": "Renamed"})
    assert renamed["title"] == "Renamed"

    _call("DELETE", f"/v1/conversations/{cid}")
    _call("GET", f"/v1/conversations/{cid}", expect=404)
    assert conversation_key(user_id, cid) not in fake_storage.data


def test_conversation_requires_owned_agent(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    _call("GET", "/v1/user/settings")  # provision the user
    missing = "00000000-0000-0000-0000-000000000000"
    _call("POST", "/v1/conversations", {"agentId": missing}, expect=404)
    _call("POST", "/v1/conversations", {"agentId": "not-a-uuid"}, expect=404)
