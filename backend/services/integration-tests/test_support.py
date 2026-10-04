"""Support threads (user <-> admin) and one-way security reports."""

from __future__ import annotations

import json

from support import load_module

user_api = load_module("backend/services/apis/user-api/handler.py", "user_api_support_handler")
admin_api = load_module("backend/services/admin/admin-console/handler.py", "admin_console_support_handler")

USER_SUB = "auth0|support-user"
ADMIN_SUB = "auth0|support-admin"


def _user_event(method: str, path: str, body=None) -> dict:
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": USER_SUB,
                        "https://get1agent.com/email": "user@example.com",
                        "https://get1agent.com/name": "User",
                    }
                }
            },
        },
        "headers": {"x-active-view": "user"},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _admin_event(method: str, path: str, body=None, admin: bool = True) -> dict:
    claims = {
        "sub": ADMIN_SUB,
        "https://get1agent.com/email": "admin@example.com",
        "https://get1agent.com/name": "Admin",
    }
    if admin:
        claims["https://get1agent.com/isAdmin"] = True
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {"jwt": {"claims": claims}},
        },
        "headers": {"x-active-view": "admin" if admin else "user"},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _user_call(method, path, body=None, expect=200):
    response = user_api.lambda_handler(_user_event(method, path, body), None)
    assert response["statusCode"] == expect, (path, response["statusCode"], response["body"])
    return json.loads(response["body"])


def _admin_call(method, path, body=None, expect=200, admin=True):
    response = admin_api.lambda_handler(_admin_event(method, path, body, admin), None)
    assert response["statusCode"] == expect, (path, response["statusCode"], response["body"])
    return json.loads(response["body"])


def test_support_thread_lifecycle() -> None:
    user_id = _user_call("GET", "/v1/user/settings")["id"]

    created = _user_call(
        "POST",
        "/v1/support/messages",
        {"subject": "Cannot upload a PDF", "body": "The upload stalls at 90%."},
        expect=201,
    )
    ticket = created["ticket"]
    assert ticket["status"] == "open"
    assert ticket["messageCount"] == 1
    ticket_id = ticket["id"]

    listed = _user_call("GET", "/v1/support/messages")["tickets"]
    assert [t["id"] for t in listed] == [ticket_id]

    thread = _user_call("GET", f"/v1/support/messages/{ticket_id}")
    assert [m["author"] for m in thread["messages"]] == ["user"]
    assert thread["messages"][0]["body"] == "The upload stalls at 90%."

    # A follow-up from the user.
    _user_call(
        "POST",
        f"/v1/support/messages/{ticket_id}/reply",
        {"body": "It also fails on Chrome."},
        expect=201,
    )

    # Admin inbox sees it and replies.
    inbox = _admin_call("GET", "/v1/admin/support")["tickets"]
    row = next(t for t in inbox if t["id"] == ticket_id)
    assert row["userId"] == user_id
    assert row["userEmail"] == "user@example.com"

    admin_thread = _admin_call("GET", f"/v1/admin/support/{user_id}/{ticket_id}")
    assert admin_thread["ticket"]["messageCount"] == 2

    _admin_call(
        "POST",
        f"/v1/admin/support/{user_id}/{ticket_id}/reply",
        {"body": "Thanks! We shipped a fix."},
        expect=201,
    )
    after = _user_call("GET", f"/v1/support/messages/{ticket_id}")
    assert [m["author"] for m in after["messages"]] == ["user", "user", "admin"]
    assert after["messages"][-1]["body"] == "Thanks! We shipped a fix."

    # Closing blocks further user replies.
    _admin_call(
        "POST",
        f"/v1/admin/support/{user_id}/{ticket_id}/status",
        {"status": "closed"},
    )
    assert _user_call("GET", "/v1/support/messages")["tickets"][0]["status"] == "closed"
    _user_call(
        "POST",
        f"/v1/support/messages/{ticket_id}/reply",
        {"body": "one more thing"},
        expect=409,
    )


def test_support_validation() -> None:
    _user_call("GET", "/v1/user/settings")
    _user_call("POST", "/v1/support/messages", {"subject": "", "body": "x"}, expect=400)
    _user_call("POST", "/v1/support/messages", {"subject": "s", "body": ""}, expect=400)
    _user_call("GET", "/v1/support/messages/does-not-exist", expect=404)


def test_security_reports_are_one_way() -> None:
    user_id = _user_call("GET", "/v1/user/settings")["id"]
    created = _user_call(
        "POST",
        "/v1/security/reports",
        {
            "url": "https://app.get1agent.com/chat",
            "page": "Chat",
            "body": "A shared link leaks the workspace id.",
        },
        expect=201,
    )
    report_id = created["report"]["id"]
    assert created["report"]["status"] == "new"
    assert created["report"]["page"] == "Chat"

    mine = _user_call("GET", "/v1/security/reports")["reports"]
    assert [r["id"] for r in mine] == [report_id]

    inbox = _admin_call("GET", "/v1/admin/security-reports")["reports"]
    row = next(r for r in inbox if r["id"] == report_id)
    assert row["userId"] == user_id
    assert row["url"].endswith("/chat")

    detail = _admin_call("GET", f"/v1/admin/security-reports/{user_id}/{report_id}")
    assert detail["report"]["body"] == "A shared link leaks the workspace id."

    updated = _admin_call(
        "POST",
        f"/v1/admin/security-reports/{user_id}/{report_id}/status",
        {"status": "resolved"},
    )
    assert updated["report"]["status"] == "resolved"


def test_security_validation_and_admin_guard() -> None:
    _user_call("GET", "/v1/user/settings")
    _user_call("POST", "/v1/security/reports", {"body": ""}, expect=400)
    _admin_call("GET", "/v1/admin/support", expect=403, admin=False)
    _admin_call("GET", "/v1/admin/security-reports", expect=403, admin=False)
