from __future__ import annotations

from typing import Any

from shared.dynamo.client import now_iso, table
from shared.dynamo.keys import NOTIF_SK, SETTINGS_SK, user_pk

DEFAULT_THEME = "dark"
DEFAULT_TIMEZONE = "UTC"
DEFAULT_EMAIL_ON_WORKFLOW_FAILURE = True
DEFAULT_CREDIT_THRESHOLD_ALERTS = True


def get_settings(sub: str) -> dict[str, Any]:
    response = table().get_item(Key={"pk": user_pk(sub), "sk": SETTINGS_SK})
    return response.get("Item") or {}


def get_notification_preferences(sub: str) -> dict[str, Any]:
    response = table().get_item(Key={"pk": user_pk(sub), "sk": NOTIF_SK})
    return response.get("Item") or {}


def ensure_settings(sub: str) -> None:
    timestamp = now_iso()
    try:
        table().put_item(
            Item={
                "pk": user_pk(sub),
                "sk": SETTINGS_SK,
                "entity": "settings",
                "preferredTheme": DEFAULT_THEME,
                "timezone": DEFAULT_TIMEZONE,
                "createdAt": timestamp,
                "updatedAt": timestamp,
            },
            ConditionExpression="attribute_not_exists(pk)",
        )
    except Exception:  # noqa: BLE001 - already exists
        pass


def ensure_notification_preferences(sub: str) -> None:
    timestamp = now_iso()
    try:
        table().put_item(
            Item={
                "pk": user_pk(sub),
                "sk": NOTIF_SK,
                "entity": "notifications",
                "emailOnWorkflowFailure": DEFAULT_EMAIL_ON_WORKFLOW_FAILURE,
                "creditThresholdAlerts": DEFAULT_CREDIT_THRESHOLD_ALERTS,
                "createdAt": timestamp,
                "updatedAt": timestamp,
            },
            ConditionExpression="attribute_not_exists(pk)",
        )
    except Exception:  # noqa: BLE001 - already exists
        pass


def update_settings(sub: str, *, preferred_theme: str | None, timezone: str | None) -> None:
    updates: list[str] = []
    names: dict[str, str] = {}
    values: dict[str, Any] = {":updated": now_iso()}
    if preferred_theme is not None:
        updates.append("preferredTheme = :theme")
        values[":theme"] = preferred_theme
    if timezone is not None:
        updates.append("#tz = :tz")
        names["#tz"] = "timezone"
        values[":tz"] = timezone
    if not updates:
        return
    updates.append("updatedAt = :updated")
    table().update_item(
        Key={"pk": user_pk(sub), "sk": SETTINGS_SK},
        UpdateExpression="SET " + ", ".join(updates),
        ExpressionAttributeValues=values,
        **({"ExpressionAttributeNames": names} if names else {}),
    )


def update_notification_preferences(
    sub: str,
    *,
    email_on_workflow_failure: bool | None,
    credit_threshold_alerts: bool | None,
) -> None:
    updates: list[str] = []
    values: dict[str, Any] = {":updated": now_iso()}
    if email_on_workflow_failure is not None:
        updates.append("emailOnWorkflowFailure = :email")
        values[":email"] = email_on_workflow_failure
    if credit_threshold_alerts is not None:
        updates.append("creditThresholdAlerts = :credit")
        values[":credit"] = credit_threshold_alerts
    if not updates:
        return
    updates.append("updatedAt = :updated")
    table().update_item(
        Key={"pk": user_pk(sub), "sk": NOTIF_SK},
        UpdateExpression="SET " + ", ".join(updates),
        ExpressionAttributeValues=values,
    )
