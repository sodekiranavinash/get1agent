"""user-api run feedback: upsert/clear + attachment to turns and runs."""

from __future__ import annotations

import json

from support import load_module, patch_lambda_storage

handler = load_module("backend/services/apis/user-api/handler.py", "user_api_handler_feedback")

SUB = "auth0|feedbacktest"


def _event(method: str, path: str, body=None) -> dict:
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": SUB,
                        "https://get1agent.com/email": "fb@example.com",
                        "https://get1agent.com/name": "FB",
                    }
                }
            },
        },
        "headers": {"x-active-view": "user"},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _call(method, path, body=None, expect=200):
    response = handler.lambda_handler(_event(method, path, body), None)
    assert response["statusCode"] == expect, (method, path, response["statusCode"], response["body"])
    return json.loads(response["body"])


def _create_agent() -> dict:
    return _call(
        "POST",
        "/v1/agents",
        {
            "name": "rated",
            "description": "d",
            "config": {
                "version": 2,
                "prompt": "You are helpful.",
                "model": "zai.glm-4.7-flash",
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
        },
        expect=201,
    )


def test_feedback_upsert_clear_and_attach(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    agent_id = _create_agent()["id"]
    user_id = _call("GET", "/v1/user/settings")["id"]

    conversation = _call("POST", "/v1/conversations", {"agentId": agent_id}, expect=201)
    cid = conversation["conversationId"]

    # Seed a turn the way the runtime does.
    from retrieval.layout import conversation_key

    fake_storage.put_json(
        conversation_key(user_id, cid),
        {
            "conversationId": cid,
            "userId": user_id,
            "turns": [
                {"runId": "run-1", "question": "hi", "status": "completed", "events": []}
            ],
        },
    )

    saved = _call(
        "PUT",
        "/v1/feedback/run-1",
        {"value": "down", "comment": "wrong answer", "categories": ["Inaccurate", "Off-topic"]},
    )
    assert saved["feedback"]["value"] == "down"
    assert saved["feedback"]["categories"] == ["Inaccurate", "Off-topic"]

    detail = _call("GET", f"/v1/conversations/{cid}")
    assert detail["turns"][0]["feedback"]["value"] == "down"
    assert detail["turns"][0]["feedback"]["comment"] == "wrong answer"

    # An empty value clears it.
    cleared = _call("PUT", "/v1/feedback/run-1", {"value": ""})
    assert cleared["feedback"]["value"] is None
    assert _call("GET", f"/v1/conversations/{cid}")["turns"][0]["feedback"] is None


def test_feedback_validation(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    _call("GET", "/v1/user/settings")  # provision the user
    _call("PUT", "/v1/feedback/run-x", {"value": "sideways"}, expect=400)
