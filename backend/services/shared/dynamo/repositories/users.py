from __future__ import annotations

import secrets
from typing import Any

from shared.dynamo.client import now_iso, table
from shared.dynamo.keys import IDENTITY_SK, PROFILE_SK, sub_pk, user_pk

# Auth0 requires namespaced custom claims on access tokens.
CLAIM_NAMESPACE = "https://get1agent.com/"

# Crockford base32 (no I, L, O, U) so ids are unambiguous and case-insensitive.
_ID_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
_ID_BODY_LEN = 16
_ID_PREFIX = "u_"


def claim(claims: dict[str, Any], name: str) -> Any:
    return claims.get(f"{CLAIM_NAMESPACE}{name}", claims.get(name))


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
