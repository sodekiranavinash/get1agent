"""Admin AI-credit management via the admin-console Lambda."""

from __future__ import annotations

import json

from support import load_module

handler = load_module("backend/services/admin/admin-console/handler.py", "admin_console_handler")

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

    # "Give this user more credits" is additive…
    updated = _call("POST", f"/v1/admin/users/{uid}/credits", {"credits": 250})
    assert updated["budgetCredits"] == 300.0
    assert get_budget(uid).budget_micro_usd == usage.credits_to_micro_usd(300)

    # …and "set the limit outright" replaces it.
    set_exact = _call(
        "POST", f"/v1/admin/users/{uid}/credits", {"credits": 400, "mode": "set"}
    )
    assert set_exact["budgetCredits"] == 400.0

    reset = _call("POST", f"/v1/admin/users/{uid}/reset")
    assert reset["spentCredits"] == 0.0


def test_admin_can_raise_their_own_credits() -> None:
    from data.repositories.quotas import get_budget
    from data.repositories.users import get_or_create_user

    me = get_or_create_user({"sub": ADMIN_SUB, "email": "admin@example.com"})
    uid = me["userId"]
    updated = _call("POST", f"/v1/admin/users/{uid}/credits", {"credits": 500})
    assert updated["budgetCredits"] == 550.0
    assert get_budget(uid).budget_micro_usd > 0
    assert "unlimited" not in updated


def test_non_admin_is_rejected() -> None:
    _call("GET", "/v1/admin/users", expect=403, admin=False)


def test_invalid_credits_rejected() -> None:
    _call("POST", "/v1/admin/users/u_x/credits", {"credits": "lots"}, expect=400)
    _call("POST", "/v1/admin/users/u_x/credits", {"credits": -5}, expect=400)


def test_admin_can_tighten_and_clear_user_limits() -> None:
    """The per-user caps are the admin's lever to restrict an abusing account."""
    from data.repositories import quotas
    from data.repositories.users import get_or_create_user

    target = get_or_create_user({"sub": "auth0|limitable", "email": "cap@example.com"})
    uid = target["userId"]

    # Defaults apply until an override is set.
    before = _call("GET", f"/v1/admin/users/{uid}/limits")
    assert before["limits"]["maxKnowledgeBases"] == {
        "value": quotas.DEFAULT_MAX_KNOWLEDGE_BASES,
        "override": False,
    }

    tightened = _call(
        "POST",
        f"/v1/admin/users/{uid}/limits",
        {"maxKnowledgeBases": 2, "maxFilesPerUser": 5, "maxStorageBytes": 1048576},
    )
    assert tightened["limits"]["maxKnowledgeBases"] == {"value": 2, "override": True}
    assert tightened["limits"]["maxFilesPerUser"] == {"value": 5, "override": True}

    # The ingestion path reads the same attributes.
    effective = quotas.get_quota(uid)
    assert effective.max_knowledge_bases == 2
    assert effective.max_files_per_user == 5

    # Blank clears the override, falling back to the platform default.
    cleared = _call(
        "POST",
        f"/v1/admin/users/{uid}/limits",
        {"maxKnowledgeBases": None, "maxFilesPerUser": None, "maxStorageBytes": None},
    )
    assert cleared["limits"]["maxKnowledgeBases"] == {
        "value": quotas.DEFAULT_MAX_KNOWLEDGE_BASES,
        "override": False,
    }
    assert quotas.get_quota(uid).max_knowledge_bases == quotas.DEFAULT_MAX_KNOWLEDGE_BASES

    _call("POST", f"/v1/admin/users/{uid}/limits", {"maxKnowledgeBases": 0}, expect=400)
    _call("POST", f"/v1/admin/users/{uid}/limits", {"nope": 1}, expect=400)
    _call("GET", f"/v1/admin/users/{uid}/limits", expect=403, admin=False)
