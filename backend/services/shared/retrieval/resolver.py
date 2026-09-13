from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import KnowledgeBase

# Safety cap so a caller cannot request an unbounded scan. Matches the default
# per-user knowledge base quota with headroom.
MAX_RESOLVED_KNOWLEDGE_BASES = 100


def _as_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _clean_names(names: Iterable[str] | None) -> list[str]:
    return [str(name).strip() for name in (names or []) if str(name).strip()]


async def resolve_knowledge_bases(
    session: AsyncSession,
    user_id: uuid.UUID,
    names: Iterable[str] | None = None,
    ids: Iterable[str] | None = None,
) -> tuple[list[KnowledgeBase], list[str]]:
    """Resolve a caller's knowledge bases by name (case-insensitive) or id.

    Returns ``(matched, not_found_names)``. When neither names nor ids are
    supplied, every knowledge base owned by the user is returned.
    """
    name_list = _clean_names(names)
    id_list = [uid for uid in (_as_uuid(value) for value in (ids or [])) if uid]

    query = select(KnowledgeBase).where(KnowledgeBase.user_id == user_id)
    if name_list or id_list:
        clauses = []
        if name_list:
            clauses.append(
                func.lower(KnowledgeBase.name).in_(
                    [name.lower() for name in name_list]
                )
            )
        if id_list:
            clauses.append(KnowledgeBase.id.in_(id_list))
        query = query.where(or_(*clauses))

    query = query.order_by(KnowledgeBase.name).limit(MAX_RESOLVED_KNOWLEDGE_BASES)
    matched = list((await session.execute(query)).scalars().all())

    matched_names = {kb.name.lower() for kb in matched}
    not_found = [name for name in name_list if name.lower() not in matched_names]
    return matched, not_found
