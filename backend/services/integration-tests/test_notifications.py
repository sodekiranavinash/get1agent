"""User notifications: the repository feed and the user-api routes."""

from __future__ import annotations

import json

from data.repositories import notifications
from data.repositories.users import upsert_user
from support import load_module

user_api = load_module("backend/services/apis/user-api/handler.py", "user_api_notifications_handler")

CLAIMS = {
    "sub": "auth0|notif-user",
    "https://get1agent.com/email": "notif@example.com",
    "https://get1agent.com/name": "Notif",
}


def _event(method: str, path: str, body=None) -> dict:
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
    return event


def _call(method: str, path: str, body=None, expect: int = 200) -> dict:
    response = user_api.lambda_handler(_event(method, path, body), None)
    assert response["statusCode"] == expect, (path, response["statusCode"], response["body"])
    return json.loads(response["body"])


def _sub() -> str:
    return upsert_user(CLAIMS)["userId"]


def test_notifications_repository_lifecycle():
    sub = _sub()
    first = notifications.create_notification(
        sub, kind="ingestion_ready", title="Ingestion finished", detail="a.pdf", link="/knowledge-bases"
    )
    second = notifications.create_notification(
        sub, kind="schedule_failed", title="Scheduled run failed", detail="flow"
    )

    listed = notifications.list_notifications(sub)
    assert {item["notificationId"] for item in listed} == {
        first["notificationId"],
        second["notificationId"],
    }
    assert notifications.unread_count(sub) == 2

    updated = notifications.mark_read(sub, first["notificationId"])
    assert updated is not None and updated["read"] is True
    assert notifications.unread_count(sub) == 1

    # Unknown id is a no-op None (the handler turns it into a 404).
    assert notifications.mark_read(sub, "00000000-0000-4000-8000-000000000000") is None

    assert notifications.mark_all_read(sub) == 1
    assert notifications.unread_count(sub) == 0

    assert notifications.delete_notification(sub, second["notificationId"]) is not None
    remaining = notifications.list_notifications(sub)
    assert [item["notificationId"] for item in remaining] == [first["notificationId"]]


def test_notification_routes():
    sub = _sub()
    created = notifications.create_notification(
        sub, kind="ingestion_ready", title="Ingestion finished", detail="a.pdf"
    )
    nid = created["notificationId"]

    payload = _call("GET", "/v1/notifications")
    assert payload["unreadCount"] == 1
    assert payload["notifications"][0]["id"] == nid
    assert payload["notifications"][0]["read"] is False
    assert payload["notifications"][0]["link"] is None

    # Clicking a notification marks it read.
    _call("POST", f"/v1/notifications/{nid}/read")
    assert _call("GET", "/v1/notifications")["unreadCount"] == 0

    # Mark-all clears the rest.
    notifications.create_notification(sub, kind="info", title="Heads up")
    assert _call("GET", "/v1/notifications")["unreadCount"] == 1
    _call("POST", "/v1/notifications/read-all")
    assert _call("GET", "/v1/notifications")["unreadCount"] == 0

    # Delete removes it from the feed.
    _call("DELETE", f"/v1/notifications/{nid}")
    assert all(item["id"] != nid for item in _call("GET", "/v1/notifications")["notifications"])

    # Unknown ids 404 rather than silently succeeding.
    unknown = "00000000-0000-4000-8000-000000000000"
    _call("POST", f"/v1/notifications/{unknown}/read", expect=404)
    _call("DELETE", f"/v1/notifications/{unknown}", expect=404)
