"""User resolution against DynamoDB.

Every user has an internal ``userId`` (a short base32 id minted on first login)
that keys all of their data: DynamoDB partitions, S3 prefixes and document
ownership. The Auth0 ``sub`` is stored on the profile and resolved to the
internal id through the ``SUB#<sub>`` identity item, so the external identity
never appears in keys.
"""

from __future__ import annotations

from typing import Any

from shared.dynamo.repositories import quotas, settings, users
from shared.dynamo.repositories.users import CLAIM_NAMESPACE, claim

__all__ = [
    "CLAIM_NAMESPACE",
    "claim",
    "get_or_create_user",
    "get_user_by_id",
    "get_user_by_sub",
]


def get_or_create_user(claims: dict[str, Any]) -> dict[str, Any]:
    """Upsert the profile and seed settings/preferences/quota on first use."""
    profile = users.upsert_user(claims)
    user_id = str(profile["userId"])
    settings.ensure_settings(user_id)
    settings.ensure_notification_preferences(user_id)
    quotas.ensure_quota(user_id)
    return profile


def get_user_by_sub(sub: str | None) -> dict[str, Any] | None:
    """Look up a user by Auth0 subject without provisioning an account."""
    return users.get_user_by_sub(sub)


def get_user_by_id(user_id: str | None) -> dict[str, Any] | None:
    """Look up a user by their internal userId without provisioning an account."""
    return users.get_user_by_id(user_id)

