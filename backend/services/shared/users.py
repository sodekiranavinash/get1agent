from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import User, UserQuota

# Auth0 requires namespaced custom claims on access tokens.
CLAIM_NAMESPACE = "https://get1agent.com/"


def claim(claims: dict[str, Any], name: str) -> Any:
    return claims.get(f"{CLAIM_NAMESPACE}{name}", claims.get(name))


async def get_or_create_user(session: AsyncSession, claims: dict[str, Any]) -> User:
    """Resolve the Auth0 subject to a `users` row, creating it on first use.

    Also seeds the per-user quota row with defaults so cap lookups are a plain
    SELECT afterwards.
    """
    sub = str(claims.get("sub") or "").strip()
    email = str(claim(claims, "email") or "").strip().lower()
    if not sub or not email:
        raise ValueError("Token is missing required claims (sub, email)")

    name = claim(claims, "name")
    full_name = name.strip()[:255] if isinstance(name, str) and name.strip() else None
    picture = claim(claims, "picture")
    picture_url = picture if isinstance(picture, str) else None
    email_verified = bool(claim(claims, "email_verified") or False)

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
        pg_insert(UserQuota)
        .values(user_id=user.id)
        .on_conflict_do_nothing(index_elements=[UserQuota.user_id])
    )

    return user
