"""DPDP consent record.

One small item per user (``USER#<userId>`` / ``#CONSENT``) recording *what* the
user consented to, the notice version they saw, whether they confirmed they are
an adult, and when (if ever) they withdrew. It lives apart from the profile so
the login-path upsert can never clobber it.

The Digital Personal Data Protection Act, 2023 requires consent to be free,
specific, informed, unconditional and unambiguous, to be capable of being
withdrawn as easily as it was given, and to be recorded by the Data Fiduciary.
The purposes below are the itemised list shown in the notice; ``required``
purposes are intrinsic to providing the service, so withdrawing them means
closing the account.
"""

from __future__ import annotations

from typing import Any

from data.client import now_iso, table
from data.keys import CONSENT_SK, user_pk

# Bump when the notice changes materially; the UI re-prompts on a mismatch.
CONSENT_VERSION = "2026-10-02"

PURPOSES: list[dict[str, Any]] = [
    {
        "id": "account",
        "title": "Account and authentication",
        "description": "Create and secure your account using your Google sign-in "
        "(name, email address and profile picture).",
        "required": True,
    },
    {
        "id": "service",
        "title": "Provide the service",
        "description": "Store and process the knowledge bases, agents, workflows, "
        "files and conversations you create so we can run them for you.",
        "required": True,
    },
    {
        "id": "ai_processing",
        "title": "AI processing by sub-processors",
        "description": "Send the prompts and content you submit to our model, "
        "embedding and search providers so your agents can answer.",
        "required": True,
    },
    {
        "id": "notifications",
        "title": "Service notifications",
        "description": "Email you about run failures, low credits and other "
        "important account events.",
        "required": False,
    },
    {
        "id": "product_analytics",
        "title": "Product analytics",
        "description": "Aggregated usage statistics that help us improve "
        "reliability. Off unless you explicitly opt in.",
        "required": False,
    },
]


def get_consent(user_id: str) -> dict[str, Any] | None:
    response = table().get_item(Key={"pk": user_pk(user_id), "sk": CONSENT_SK})
    return response.get("Item")


def record_consent(
    user_id: str,
    *,
    purposes: list[str],
    adult_confirmed: bool,
    language: str = "en",
) -> dict[str, Any]:
    timestamp = now_iso()
    item: dict[str, Any] = {
        "pk": user_pk(user_id),
        "sk": CONSENT_SK,
        "entity": "consent",
        "consentVersion": CONSENT_VERSION,
        "purposes": list(purposes),
        "adultConfirmed": bool(adult_confirmed),
        "language": language or "en",
        "acceptedAt": timestamp,
        "updatedAt": timestamp,
    }
    table().put_item(Item=item)
    return item


def withdraw_consent(user_id: str) -> dict[str, Any] | None:
    """Mark consent withdrawn (kept for the record; never silently deleted)."""
    existing = get_consent(user_id)
    if existing is None:
        return None
    timestamp = now_iso()
    table().update_item(
        Key={"pk": user_pk(user_id), "sk": CONSENT_SK},
        UpdateExpression="SET withdrawnAt = :w, updatedAt = :u",
        ExpressionAttributeValues={":w": timestamp, ":u": timestamp},
    )
    existing["withdrawnAt"] = timestamp
    existing["updatedAt"] = timestamp
    return existing
