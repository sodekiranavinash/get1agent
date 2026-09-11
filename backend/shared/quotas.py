from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import UserQuota
from shared.models.user_quota import (
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_MAX_FILES_PER_KB,
    DEFAULT_MAX_FILES_PER_USER,
    DEFAULT_MAX_KNOWLEDGE_BASES,
    DEFAULT_MAX_STORAGE_BYTES,
)


@dataclass(frozen=True)
class Quota:
    max_file_bytes: int
    max_files_per_kb: int
    max_knowledge_bases: int
    max_files_per_user: int
    max_storage_bytes: int


async def get_quota(session: AsyncSession, user_id: uuid.UUID) -> Quota:
    """Return the user's caps, falling back to the global defaults."""
    row = (
        await session.execute(select(UserQuota).where(UserQuota.user_id == user_id))
    ).scalar_one_or_none()
    if row is None:
        return Quota(
            max_file_bytes=DEFAULT_MAX_FILE_BYTES,
            max_files_per_kb=DEFAULT_MAX_FILES_PER_KB,
            max_knowledge_bases=DEFAULT_MAX_KNOWLEDGE_BASES,
            max_files_per_user=DEFAULT_MAX_FILES_PER_USER,
            max_storage_bytes=DEFAULT_MAX_STORAGE_BYTES,
        )
    return Quota(
        max_file_bytes=row.max_file_bytes,
        max_files_per_kb=row.max_files_per_kb,
        max_knowledge_bases=row.max_knowledge_bases,
        max_files_per_user=row.max_files_per_user,
        max_storage_bytes=row.max_storage_bytes,
    )
