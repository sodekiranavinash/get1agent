"""Admin → AI Assistant routes: config round-trip, owner-scoped reads, guards."""
from __future__ import annotations

import json

from support import load_module

handler = load_module(
    "backend/services/admin/admin-console/handler.py", "admin_ai_assistant_handler"
)

ADMIN_SUB = "auth0|avitestadmin"


def _event(method: str, path: str, body=None, query=None) -> dict:
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": ADMIN_SUB,
                        "https://get1agent.com/email": "ai-assistant-admin@example.com",
                        "https://get1agent.com/roles": ["admin"],
                    }
                }
            },
        },
        "headers": {"x-active-view": "admin"},
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


def test_get_config_returns_settings_and_models():
    data = _call("GET", "/v1/admin/ai-assistant")
    assert data["settings"]["enabled"] is True
    assert data["settings"]["model"]
    assert any(choice["id"] == "zai.glm-4.7-flash" for choice in data["modelChoices"])
    assert "enabled" in data["editable"]
    assert "guestPerHour" in data["editable"]


def test_post_updates_config_and_stamps_the_actor():
    data = _call("POST", "/v1/admin/ai-assistant", {"enabled": False, "guestPerHour": 3})
    assert data["settings"]["enabled"] is False
    assert data["settings"]["guestPerHour"] == 3
    assert data["updatedBy"] == "ai-assistant-admin@example.com"

    config = _call("GET", "/v1/admin/ai-assistant")
    assert config["settings"]["enabled"] is False

    # Restore, so the other tests are not affected by the kill switch.
    _call("POST", "/v1/admin/ai-assistant", {"enabled": True, "guestPerHour": 6})


def test_post_rejects_unknown_fields():
    _call("POST", "/v1/admin/ai-assistant", {"nope": 1}, expect=400)
    _call("POST", "/v1/admin/ai-assistant", {}, expect=400)


def test_owner_scoped_reads_explain_themselves_without_a_user():
    for path in ("/v1/admin/ai-assistant/feedback", "/v1/admin/ai-assistant/traces", "/v1/admin/ai-assistant/conversations"):
        data = _call("GET", path)
        assert data["items"] == []
        assert "userId" in data["note"]

    with_user = _call("GET", "/v1/admin/ai-assistant/feedback", query={"userId": "u_7k3f9qz2mpx8n4rq"})
    assert with_user["userId"] == "u_7k3f9qz2mpx8n4rq"
    assert with_user["items"] == []


def test_trace_and_conversation_lookups_are_validated():
    _call("GET", "/v1/admin/ai-assistant/traces/u_x/t_missing", expect=404)
    _call("GET", "/v1/admin/ai-assistant/conversations/u_x/c_missing", expect=404)


def test_knowledge_reports_the_corpus_scope():
    data = _call("GET", "/v1/admin/ai-assistant/knowledge")
    assert data["scope"] == "platform"
    assert data["kbId"]
    assert "rebuildCommand" in data
    assert isinstance(data["statuses"], dict)


def test_unknown_subroute_is_404_and_bad_method_is_405():
    _call("GET", "/v1/admin/ai-assistant/nonsense", expect=404)
    _call("DELETE", "/v1/admin/ai-assistant", expect=405)


def test_feedback_filters_ride_in_the_query_string():
    """`?value=up` must reach the repository — it is a query param, not a body."""
    from data.repositories import ai_assistant as ai_assistant_repo

    user_id = "u_avifeedback00000001"
    ai_assistant_repo.upsert_feedback(user_id, "avirun_up", value="up", question="how do I add a KB?")
    ai_assistant_repo.upsert_feedback(user_id, "avirun_down", value="down", question="that was wrong")

    only_up = _call("GET", "/v1/admin/ai-assistant/feedback", query={"userId": user_id, "value": "up"})
    assert [item["runId"] for item in only_up["items"]] == ["avirun_up"]

    everything = _call("GET", "/v1/admin/ai-assistant/feedback", query={"userId": user_id})
    assert {item["runId"] for item in everything["items"]} == {"avirun_up", "avirun_down"}
