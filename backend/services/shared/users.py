"""User resolution against DynamoDB.

The caller's Auth0 subject (``sub``) is the user id everywhere: DynamoDB keys,
S3 prefixes and document ownership. There is no surrogate UUID any more.
"""

from __future__ import annotations

from typing import Any

from shared.dynamo.repositories import quotas, settings, users
from shared.dynamo.repositories.users import CLAIM_NAMESPACE, claim

__all__ = [
    "CLAIM_NAMESPACE",
    "claim",
    "get_or_create_user",
    "get_user_by_sub",
]


def get_or_create_user(claims: dict[str, Any]) -> dict[str, Any]:
    """Upsert the profile and seed settings/preferences/quota on first use."""
    profile = users.upsert_user(claims)
    sub = str(profile["userId"])
    settings.ensure_settings(sub)
    settings.ensure_notification_preferences(sub)
    quotas.ensure_quota(sub)
    return profile


def get_user_by_sub(sub: str | None) -> dict[str, Any] | None:
    """Look up a user by Auth0 subject without provisioning an account."""
    return users.get_user_by_sub(sub)
