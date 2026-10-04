"""User notifications feed.

One small item per notification under the user's partition
(``USER#<userId>`` / ``NOTIF#<id>``). Distinct from the ``#NOTIF``
notification-*preferences* item managed by ``data.repositories.settings``.

Notifications are tiny metadata; the feed is read with a base-table Query on
``USER#<userId>`` and the ``NOTIF#`` prefix (never a Scan). Items carry a TTL
(``expiresAt``) so the feed self-prunes.
"""

from __future__ import annotations

import uuid
from typing import Any

from data.client import is_conditional_failure, now_iso, table, ttl_epoch
from data.keys import NOTIFICATION_PREFIX, notification_sk, user_pk

# Feed items expire after 90 days (DynamoDB TTL on `expiresAt`).
TTL_DAYS = 90
# Hard cap on how many notifications a single list call returns.
MAX_LIST = 100


def _query(user_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": {":pk": user_pk(user_id), ":prefix": NOTIFICATION_PREFIX},
    }
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


def create_notification(
    user_id: str,
    *,
    kind: str,
    title: str,
    detail: str = "",
    link: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one notification to the user's feed.

    ``kind`` is a short machine tag the SPA maps to an icon/colour
    (e.g. ``ingestion_ready``, ``ingestion_failed``, ``schedule_failed``).
    ``link`` is an in-app path opened when the notification is clicked.
    """
    notification_id = str(uuid.uuid4())
    timestamp = now_iso()
    item = {
        "pk": user_pk(user_id),
        "sk": notification_sk(notification_id),
        "entity": "notification",
        "notificationId": notification_id,
        "userId": user_id,
        "kind": kind,
        "title": title,
        "detail": detail,
        "link": link,
        "read": False,
        "metadata": metadata or {},
        "createdAt": timestamp,
        "expiresAt": ttl_epoch(TTL_DAYS),
    }
    table().put_item(Item=item)
    return item


def list_notifications(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Newest-first notifications for the user (bounded by ``limit``)."""
    items = _query(user_id)
    items.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    return items[: max(1, min(int(limit), MAX_LIST))]


def unread_count(user_id: str) -> int:
    return sum(1 for item in _query(user_id) if not item.get("read"))


def get_notification(user_id: str, notification_id: str) -> dict[str, Any] | None:
    response = table().get_item(
        Key={"pk": user_pk(user_id), "sk": notification_sk(notification_id)}
    )
    return response.get("Item")


def mark_read(user_id: str, notification_id: str) -> dict[str, Any] | None:
    """Mark one notification read. Returns the updated item, or None if absent."""
    timestamp = now_iso()
    try:
        response = table().update_item(
            Key={"pk": user_pk(user_id), "sk": notification_sk(notification_id)},
            UpdateExpression="SET #read = :true, readAt = :ts",
            ExpressionAttributeNames={"#read": "read"},
            ExpressionAttributeValues={":true": True, ":ts": timestamp},
            ConditionExpression="attribute_exists(pk)",
            ReturnValues="ALL_NEW",
        )
    except Exception as exc:  # noqa: BLE001
        if is_conditional_failure(exc):
            return None
        raise
    return response.get("Attributes")


def mark_all_read(user_id: str) -> int:
    """Mark every unread notification read; returns how many were changed."""
    timestamp = now_iso()
    changed = 0
    for item in _query(user_id):
        if item.get("read"):
            continue
        table().update_item(
            Key={"pk": item["pk"], "sk": item["sk"]},
            UpdateExpression="SET #read = :true, readAt = :ts",
            ExpressionAttributeNames={"#read": "read"},
            ExpressionAttributeValues={":true": True, ":ts": timestamp},
        )
        changed += 1
    return changed


def delete_notification(user_id: str, notification_id: str) -> dict[str, Any] | None:
    response = table().delete_item(
        Key={"pk": user_pk(user_id), "sk": notification_sk(notification_id)},
        ReturnValues="ALL_OLD",
    )
    return response.get("Attributes")
