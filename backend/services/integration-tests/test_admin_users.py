"""Admin AI-credit management via the admin (mcp-tester) Lambda."""

from __future__ import annotations

import json

from support import load_module

handler = load_module("backend/services/admin/mcp-tester/handler.py", "mcp_tester_handler")

ADMIN_SUB = "auth0|admin-user"


def _event(method: str, path: str, body=None, query=None, admin: bool = True) -> dict:
    claims = {"sub": ADMIN_SUB, "https://get1agent.com/email": "admin@example.com"}
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
    if query:
        event["rawQueryString"] = "&".join(f"{k}={v}" for k, v in query.items())
    return event


def _call(method: str, path: str, body=None, query=None, expect: int = 200, admin: bool = True):
    response = handler.lambda_handler(_event(method, path, body, query, admin), None)
    assert response["statusCode"] == expect, response["body"]
    return json.loads(response["body"])


def test_admin_lists_users_and_grants_credits() -> None:
    from core import usage
    from data.repositories.quotas import get_budget
    from data.repositories.users import get_or_create_user

    target = get_or_create_user(
        {"sub": "auth0|target", "email": "target@example.com"}
    )
    uid = target["userId"]

    listed = _call("GET", "/v1/admin/users")
    userIds = {user["userId"] for user in listed["users"]}
    assert uid in userIds
    assert listed["defaultCredits"] == 50.0
    assert listed["creditsPerUsd"] == 100.0
    target_row = next(user for user in listed["users"] if user["userId"] == uid)
    assert target_row["budgetCredits"] == 50.0
    assert target_row["spentCredits"] == 0.0

    updated = _call("POST", f"/v1/admin/users/{uid}/credits", {"credits": 250})
    assert updated["budgetCredits"] == 250.0
    assert get_budget(uid).budget_micro_usd == usage.credits_to_micro_usd(250)

    reset = _call("POST", f"/v1/admin/users/{uid}/reset")
    assert reset["spentCredits"] == 0.0


def test_admin_can_raise_their_own_credits() -> None:
    from data.repositories.quotas import get_budget
    from data.repositories.users import get_or_create_user

    me = get_or_create_user({"sub": ADMIN_SUB, "email": "admin@example.com"})
    uid = me["userId"]
    updated = _call("POST", f"/v1/admin/users/{uid}/credits", {"credits": 500})
    assert updated["budgetCredits"] == 500.0
    assert get_budget(uid).budget_micro_usd > 0


def test_non_admin_is_rejected() -> None:
    _call("GET", "/v1/admin/users", expect=403, admin=False)


def test_invalid_credits_rejected() -> None:
    _call("POST", "/v1/admin/users/u_x/credits", {"credits": "lots"}, expect=400)
    _call("POST", "/v1/admin/users/u_x/credits", {"credits": -5}, expect=400)
