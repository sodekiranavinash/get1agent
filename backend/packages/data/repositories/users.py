from __future__ import annotations

import secrets
from typing import Any

from data.client import now_iso, table
from data.keys import (
    EVAL_RUN_PREFIX,
    GSI3,
    IDENTITY_SK,
    PROFILE_SK,
    SUPPORT_PREFIX,
    eval_results_pk,
    sub_pk,
    support_partition_pk,
    user_pk,
)

# Shared GSI3 partition listing every user profile (admin console). Sparse: an
# item only appears once it carries the ``gsi3pk`` attribute.
USERS_ALL_PK = "USERS#all"

# Auth0 requires namespaced custom claims on access tokens.
CLAIM_NAMESPACE = "https://get1agent.com/"

# Crockford base32 (no I, L, O, U) so ids are unambiguous and case-insensitive.
_ID_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
_ID_BODY_LEN = 16
_ID_PREFIX = "u_"


def claim(claims: dict[str, Any], name: str) -> Any:
    return claims.get(f"{CLAIM_NAMESPACE}{name}", claims.get(name))


def is_admin_claims(claims: dict[str, Any]) -> bool:
    """True when the token carries the admin role (mirrors ``core.auth``)."""
    if claim(claims, "isAdmin"):
        return True
    roles = claim(claims, "roles") or []
    if isinstance(roles, str):
        roles = [roles]
    if not isinstance(roles, list):
        return False
    return any(str(role).strip().lower() == "admin" for role in roles)


def _new_user_id() -> str:
    """Mint a short, unguessable user id, e.g. ``u_7k3f9qz2mpx8n4rq``."""
    body = "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_BODY_LEN))
    return f"{_ID_PREFIX}{body}"


def _is_conditional_failure(exc: BaseException) -> bool:
    from botocore.exceptions import ClientError

    return (
        isinstance(exc, ClientError)
        and exc.response.get("Error", {}).get("Code")
        == "ConditionalCheckFailedException"
    )


def _profile_item(
    claims: dict[str, Any],
    *,
    existing: dict[str, Any] | None,
    user_id: str,
) -> dict[str, Any]:
    sub = str(claims.get("sub") or "").strip()
    email = str(claim(claims, "email") or "").strip().lower()
    if not sub or not email:
        raise ValueError("Token is missing required claims (sub, email)")

    name = claim(claims, "name")
    full_name = name.strip()[:255] if isinstance(name, str) and name.strip() else None
    picture = claim(claims, "picture")
    picture_url = picture if isinstance(picture, str) else None
    email_verified = bool(claim(claims, "email_verified") or False)
    timestamp = now_iso()

    item: dict[str, Any] = {
        "pk": user_pk(user_id),
        "sk": PROFILE_SK,
        "entity": "user",
        "userId": user_id,
        "sub": sub,
        "email": email,
        "emailVerified": email_verified,
        "pictureUrl": picture_url,
        "lastLoginAt": timestamp,
        "updatedAt": timestamp,
    }
    # ``fullName`` is only overwritten when the token carries one, so a profile
    # edit is not clobbered by a token that omits the claim.
    if full_name is not None:
        item["fullName"] = full_name
    elif existing and existing.get("fullName"):
        item["fullName"] = existing["fullName"]
    item["createdAt"] = (existing or {}).get("createdAt") or timestamp
    item["isAdmin"] = is_admin_claims(claims)
    # Project the profile onto GSI3 so the admin console can list users without
    # a Scan. Newest first via the ``<createdAt>#<userId>`` sort key.
    if sub:
        item[GSI3[0]] = USERS_ALL_PK
        item[GSI3[1]] = f"{item['createdAt']}#{user_id}"
    return item


def _get_identity(sub: str) -> dict[str, Any] | None:
    """The ``SUB#<sub>`` item that maps an Auth0 sub to the internal userId."""
    response = table().get_item(
        Key={"pk": sub_pk(sub), "sk": IDENTITY_SK}, ConsistentRead=True
    )
    return response.get("Item")


def _claim_identity(sub: str, user_id: str) -> bool:
    """Atomically bind ``sub`` to ``user_id``; False if it is already bound."""
    try:
        table().put_item(
            Item={
                "pk": sub_pk(sub),
                "sk": IDENTITY_SK,
                "entity": "user_identity",
                "userId": user_id,
                "createdAt": now_iso(),
            },
            ConditionExpression="attribute_not_exists(pk)",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        if _is_conditional_failure(exc):
            return False
        raise


def _put_profile_if_absent(item: dict[str, Any]) -> bool:
    """Create the profile only if its ``USER#<userId>`` partition is free."""
    try:
        table().put_item(
            Item=item, ConditionExpression="attribute_not_exists(pk)"
        )
        return True
    except Exception as exc:  # noqa: BLE001
        if _is_conditional_failure(exc):
            return False
        raise


def get_user_by_id(user_id: str | None) -> dict[str, Any] | None:
    normalized = str(user_id or "").strip()
    if not normalized:
        return None
    response = table().get_item(
        Key={"pk": user_pk(normalized), "sk": PROFILE_SK}, ConsistentRead=True
    )
    return response.get("Item")


def list_users(
    limit: int = 25, exclusive_start_key: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """A page of user profiles (newest first) for the admin console.

    Uses the shared GSI3 partition — never a Scan. Returns the items and the
    ``LastEvaluatedKey`` to pass back as a cursor.
    """
    kwargs: dict[str, Any] = {
        "IndexName": "byStatus",
        "KeyConditionExpression": f"{GSI3[0]} = :pk",
        "ExpressionAttributeValues": {":pk": USERS_ALL_PK},
        "ScanIndexForward": False,
        "Limit": max(1, min(int(limit), 100)),
    }
    if exclusive_start_key:
        kwargs["ExclusiveStartKey"] = exclusive_start_key
    response = table().query(**kwargs)
    return response.get("Items") or [], response.get("LastEvaluatedKey")


def get_user_by_sub(sub: str | None) -> dict[str, Any] | None:
    normalized = str(sub or "").strip()
    if not normalized:
        return None
    identity = _get_identity(normalized)
    if not identity:
        return None
    return get_user_by_id(identity.get("userId"))


def _create_user(
    claims: dict[str, Any], sub: str
) -> tuple[str, dict[str, Any] | None]:
    """Mint a unique short userId and bind it to the Auth0 sub.

    A conditional create on ``USER#<userId>`` guarantees the short id is unique
    (regenerate on collision). Binding the ``sub`` is a separate conditional
    write, so a concurrent first login cannot create a second profile.
    """
    item: dict[str, Any] | None = None
    for _ in range(8):
        candidate = _new_user_id()
        item = _profile_item(claims, existing=None, user_id=candidate)
        if _put_profile_if_absent(item):
            break
    else:
        raise RuntimeError("Could not allocate a unique user id")

    user_id = str(item["userId"])
    if sub and not _claim_identity(sub, user_id):
        identity = _get_identity(sub)
        winner = str((identity or {}).get("userId") or "")
        if winner and winner != user_id:
            table().delete_item(Key={"pk": user_pk(user_id), "sk": PROFILE_SK})
            return winner, get_user_by_id(winner)
    return user_id, item


def upsert_user(claims: dict[str, Any]) -> dict[str, Any]:
    """Create or refresh the caller's profile row and return it."""
    sub = str(claims.get("sub") or "").strip()
    identity = _get_identity(sub) if sub else None
    existing: dict[str, Any] | None = None
    if identity and identity.get("userId"):
        user_id = str(identity["userId"])
        existing = get_user_by_id(user_id)
    else:
        user_id, existing = _create_user(claims, sub)

    item = _profile_item(claims, existing=existing, user_id=user_id)
    table().put_item(Item=item)
    return item


def get_or_create_user(claims: dict[str, Any]) -> dict[str, Any]:
    """Upsert the profile and seed settings/preferences/quota on first use."""
    from data.repositories import quotas, settings

    profile = upsert_user(claims)
    user_id = str(profile["userId"])
    settings.ensure_settings(user_id)
    settings.ensure_notification_preferences(user_id)
    # Admins get a larger application-token budget ($20 vs the $2 default).
    quotas.ensure_quota(user_id, is_admin=is_admin_claims(claims))
    return profile


# --- account closure (DPDP right to erasure) ----------------------------------


def list_user_items(user_id: str) -> list[dict[str, Any]]:
    """Every item in the user's partition, paginated (never a Scan)."""
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk",
        "ExpressionAttributeValues": {":pk": user_pk(user_id)},
    }
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


def _delete_partition(pk: str) -> int:
    """Delete every item under one partition; returns how many were removed."""
    deleted = 0
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk",
        "ExpressionAttributeValues": {":pk": pk},
    }
    while True:
        response = table().query(**kwargs)
        for item in response.get("Items") or []:
            table().delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
            deleted += 1
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return deleted


def delete_user_data(user_id: str) -> dict[str, int]:
    """Erase every item owned by the user.

    The user's dataset hangs off ``USER#<userId>`` plus the
    ``EVALRUN#<runId>`` and ``SUPPORT#<ticketId>`` partitions those items point
    at (per-case eval results and support messages live in their own
    partitions). Everything is deleted item-by-item via targeted queries — no
    ``Scan``.
    """
    items = list_user_items(user_id)

    eval_run_ids: list[str] = []
    ticket_ids: list[str] = []
    for item in items:
        sk = str(item.get("sk") or "")
        if sk.startswith(EVAL_RUN_PREFIX):
            eval_run_ids.append(sk[len(EVAL_RUN_PREFIX):])
        elif sk.startswith(SUPPORT_PREFIX):
            ticket_ids.append(sk[len(SUPPORT_PREFIX):])

    deleted = {"userItems": 0, "evalRunItems": 0, "supportItems": 0}
    for run_id in eval_run_ids:
        deleted["evalRunItems"] += _delete_partition(eval_results_pk(run_id))
    for ticket_id in ticket_ids:
        deleted["supportItems"] += _delete_partition(support_partition_pk(ticket_id))
    for item in items:
        table().delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
        deleted["userItems"] += 1
    return deleted


def delete_identity(sub: str) -> None:
    """Remove the ``sub -> userId`` binding so a later login starts fresh."""
    normalized = str(sub or "").strip()
    if normalized:
        table().delete_item(Key={"pk": sub_pk(normalized), "sk": IDENTITY_SK})
