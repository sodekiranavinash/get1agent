from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import UserQuota
from shared.models.user_quota import DEFAULT_MAX_FILE_BYTES, DEFAULT_MAX_FILES_PER_KB


@dataclass(frozen=True)
class Quota:
    max_file_bytes: int
    max_files_per_kb: int


async def get_quota(session: AsyncSession, user_id: uuid.UUID) -> Quota:
    """Return the user's caps, falling back to the global defaults."""
    row = (
        await session.execute(select(UserQuota).where(UserQuota.user_id == user_id))
    ).scalar_one_or_none()
    if row is None:
        return Quota(DEFAULT_MAX_FILE_BYTES, DEFAULT_MAX_FILES_PER_KB)
    return Quota(row.max_file_bytes, row.max_files_per_kb)
