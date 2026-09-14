from __future__ import annotations

from typing import Any

from shared.dynamo.client import now_iso, table
from shared.dynamo.keys import PROFILE_SK, user_pk

# Auth0 requires namespaced custom claims on access tokens.
CLAIM_NAMESPACE = "https://get1agent.com/"


def claim(claims: dict[str, Any], name: str) -> Any:
    return claims.get(f"{CLAIM_NAMESPACE}{name}", claims.get(name))


def _profile_item(claims: dict[str, Any], *, existing: dict[str, Any] | None) -> dict[str, Any]:
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
        "pk": user_pk(sub),
        "sk": PROFILE_SK,
        "entity": "user",
        "userId": sub,
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


def get_user_by_sub(sub: str | None) -> dict[str, Any] | None:
    normalized = str(sub or "").strip()
    if not normalized:
        return None
    response = table().get_item(Key={"pk": user_pk(normalized), "sk": PROFILE_SK})
    return response.get("Item")


def upsert_user(claims: dict[str, Any]) -> dict[str, Any]:
    """Create or refresh the caller's profile row and return it."""
    sub = str(claims.get("sub") or "").strip()
    existing = get_user_by_sub(sub)
    item = _profile_item(claims, existing=existing)
    table().put_item(Item=item)
    return item
