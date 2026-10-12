"""Avi feedback through the route the browser can actually reach.

The widget cannot mint the MicroVM ingress token, so it posts a thumb to
``POST /v1/avi/feedback`` on user-api. This test drives that route against the
moto-backed table and then reads the item back through the admin repository, which
is the pair that has to agree: if the route wrote a different item shape, the
admin feedback table would silently show nothing.
"""

from __future__ import annotations

import json

from support import load_module, patch_lambda_storage

handler = load_module("backend/services/apis/user-api/handler.py", "user_api_handler_avi")

SUB = "auth0|avifeedback"

ADMIN = load_module(
    "backend/services/admin/admin-console/src/avi.py", "admin_avi_feedback"
)


def _event(method: str, path: str, body=None) -> dict:
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": SUB,
                        "https://get1agent.com/email": "avi@example.com",
                        "https://get1agent.com/name": "Avi Tester",
                    }
                }
            },
        },
        "headers": {"x-active-view": "user"},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _call(method, path, body=None, expect=200) -> dict:
    response = handler.lambda_handler(_event(method, path, body), None)
    assert response["statusCode"] == expect, (
        method,
        path,
        response["statusCode"],
        response["body"],
    )
    return json.loads(response["body"])


def test_avi_feedback_is_stored_and_listed_for_admins(fake_storage, monkeypatch):
    from data.repositories import avi as avi_repo

    patch_lambda_storage(monkeypatch, handler, fake_storage)

    # Provision the caller's profile so the route has a userId to write under.
    profile = _call("GET", "/v1/user/settings")
    user_id = profile["id"]

    saved = _call(
        "POST",
        "/v1/avi/feedback",
        {
            "runId": "avirun_route_1",
            "value": "down",
            "comment": "the answer cited the wrong page",
            "question": "where do I rotate a vault secret?",
            "answerPreview": "Open Settings…",
            "conversationId": "avi_0000000000001_ab",
            "model": "nvidia.nemotron-nano-3-30b",
            "classifierKind": "platform",
            "intent": "howto",
            "latencyMs": 1800,
            "tokensIn": 120,
            "tokensOut": 90,
            "sources": [{"title": "Vault", "route": "/vault"}],
        },
    )
    assert saved == {"stored": True, "runId": "avirun_route_1"}

    # What the admin page reads back, through the same repository the admin
    # Lambda uses (owner-scoped, one Query, no Scan).
    items, _cursor = avi_repo.list_feedback(user_id, limit=50)
    assert len(items) == 1
    item = items[0]
    assert item["runId"] == "avirun_route_1"
    assert item["value"] == "down"
    assert item["comment"] == "the answer cited the wrong page"
    assert item["question"] == "where do I rotate a vault secret?"
    assert item["classifierKind"] == "platform"
    assert item["sources"] == [{"title": "Vault", "route": "/vault"}]
    # Avi writes only Avi prefixes, so nothing here can surface as agent feedback.
    assert item["sk"].startswith("AVIFEEDBACK#")

    # The admin module renders that same list for the page.
    admin_view = json.loads(
        ADMIN.route(
            {"email": "admin@example.com"},
            "GET",
            ["v1", "admin", "avi", "feedback"],
            {},
            {"userId": user_id},
        )["body"]
    )
    assert admin_view["items"][0]["runId"] == "avirun_route_1"

    # Re-rating the same run updates the one item rather than adding another.
    _call("POST", "/v1/avi/feedback", {"runId": "avirun_route_1", "value": "up"})
    items, _cursor = avi_repo.list_feedback(user_id, limit=50)
    assert len(items) == 1
    assert items[0]["value"] == "up"


def test_avi_feedback_validation_and_ownership(fake_storage, monkeypatch):
    from data.repositories import avi as avi_repo

    patch_lambda_storage(monkeypatch, handler, fake_storage)
    profile = _call("GET", "/v1/user/settings")

    _call("POST", "/v1/avi/feedback", {"value": "sideways", "runId": "r"}, expect=400)
    _call("POST", "/v1/avi/feedback", {"value": "up"}, expect=400)
    # A verb other than POST is rejected, not silently accepted.
    _call("GET", "/v1/avi/feedback", expect=405)

    # Nothing was written by the rejected calls.
    items, _cursor = avi_repo.list_feedback(profile["id"], limit=50)
    assert items == []
