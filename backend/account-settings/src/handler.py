import asyncio
import base64
import json
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.session import get_session
from shared.models import User, UserNotificationPreferences, UserSettings

VALID_THEMES = {"light", "dark"}
# Auth0 requires namespaced custom claims on access tokens.
CLAIM_NAMESPACE = "https://get1agent.com/"


def _claim(claims: dict[str, Any], name: str) -> Any:
    return claims.get(f"{CLAIM_NAMESPACE}{name}", claims.get(name))


def _json(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _claims(event: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]
    except (KeyError, TypeError):
        return None


def _method(event: dict[str, Any]) -> str:
    return str(event.get("requestContext", {}).get("http", {}).get("method", event.get("httpMethod", "GET"))).upper()


def _body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body")
    if not raw:
        return {}
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Request body must be a JSON object")
    return parsed


def _serialize(
    user: User,
    settings: UserSettings,
    prefs: UserNotificationPreferences,
) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "emailVerified": user.email_verified,
        "fullName": user.full_name,
        "pictureUrl": user.picture_url,
        "preferredTheme": settings.preferred_theme,
        "timezone": settings.timezone,
        "emailOnWorkflowFailure": prefs.email_on_workflow_failure,
        "creditThresholdAlerts": prefs.credit_threshold_alerts,
    }


def _validated_full_name(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("fullName must be a string")
    name = value.strip()
    if len(name) > 255:
        raise ValueError("fullName must be at most 255 characters")
    return name or None


def _validated_theme(value: Any) -> str:
    if not isinstance(value, str) or value not in VALID_THEMES:
        raise ValueError("preferredTheme must be one of: light, dark")
    return value


def _validated_timezone(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ValueError("timezone must be a valid IANA timezone name")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA timezone name") from exc
    return value


def _validated_toggle(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


async def _get_or_create(
    session: AsyncSession,
    claims: dict[str, Any],
) -> tuple[User, UserSettings, UserNotificationPreferences]:
    sub = str(claims.get("sub") or "").strip()
    email = str(_claim(claims, "email") or "").strip().lower()
    if not sub or not email:
        raise ValueError("Token is missing required claims (sub, email)")

    full_name = _validated_full_name(_claim(claims, "name"))
    picture = _claim(claims, "picture")
    picture_url = picture if isinstance(picture, str) else None
    email_verified = bool(_claim(claims, "email_verified") or False)

    await session.execute(
        pg_insert(User)
        .values(
            auth0_sub=sub,
            email=email,
            email_verified=email_verified,
            full_name=full_name,
            picture_url=picture_url,
            last_login_at=func.now(),
        )
        .on_conflict_do_update(
            index_elements=[User.auth0_sub],
            set_={
                "email": email,
                "email_verified": email_verified,
                "picture_url": picture_url,
                "last_login_at": func.now(),
                "updated_at": func.now(),
            },
        )
    )

    user = (await session.execute(select(User).where(User.auth0_sub == sub))).scalar_one()

    await session.execute(
        pg_insert(UserSettings)
        .values(user_id=user.id)
        .on_conflict_do_nothing(index_elements=[UserSettings.user_id])
    )
    await session.execute(
        pg_insert(UserNotificationPreferences)
        .values(user_id=user.id)
        .on_conflict_do_nothing(index_elements=[UserNotificationPreferences.user_id])
    )

    settings = (
        await session.execute(select(UserSettings).where(UserSettings.user_id == user.id))
    ).scalar_one()
    prefs = (
        await session.execute(
            select(UserNotificationPreferences).where(
                UserNotificationPreferences.user_id == user.id
            )
        )
    ).scalar_one()

    return user, settings, prefs


async def _handle_get(claims: dict[str, Any]) -> dict[str, Any]:
    async with get_session() as session:
        user, settings, prefs = await _get_or_create(session, claims)
        await session.commit()
        return _json(200, _serialize(user, settings, prefs))


async def _handle_post(claims: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    async with get_session() as session:
        user, settings, prefs = await _get_or_create(session, claims)

        if "fullName" in body:
            user.full_name = _validated_full_name(body["fullName"])
        if "preferredTheme" in body:
            settings.preferred_theme = _validated_theme(body["preferredTheme"])
        if "timezone" in body:
            settings.timezone = _validated_timezone(body["timezone"])
        if "emailOnWorkflowFailure" in body:
            prefs.email_on_workflow_failure = _validated_toggle(
                "emailOnWorkflowFailure", body["emailOnWorkflowFailure"]
            )
        if "creditThresholdAlerts" in body:
            prefs.credit_threshold_alerts = _validated_toggle(
                "creditThresholdAlerts", body["creditThresholdAlerts"]
            )

        await session.commit()
        return _json(200, _serialize(user, settings, prefs))


def lambda_handler(event: dict[str, Any], _context) -> dict[str, Any]:
    claims = _claims(event)
    if not claims:
        return _json(401, {"error": "Unauthorized"})

    method = _method(event)
    try:
        if method == "GET":
            return asyncio.run(_handle_get(claims))
        if method == "POST":
            return asyncio.run(_handle_post(claims, _body(event)))
        return _json(405, {"error": f"Method not allowed: {method}"})
    except ValueError as exc:
        return _json(400, {"error": str(exc)})
    except Exception as exc:
        print(f"account-settings error: {exc}")
        return _json(500, {"error": "Internal server error"})
