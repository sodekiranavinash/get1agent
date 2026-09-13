from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from shared.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from shared.models.document import Document
    from shared.models.knowledge_base import KnowledgeBase
    from shared.models.user import User


class DocumentParent(Base, TimestampMixin):
    """A larger context unit returned to the model (small-to-big retrieval).

    For paginated formats (PDF) a parent is a source page; a page that is too
    large becomes several parents sharing the same page number. For every other
    format a parent is a fixed-size window of the document. Only the child
    chunks are embedded; the parent's ``content`` is what gets handed back for
    context once a child matches.
    """

    __tablename__ = "document_parents"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "ordinal", name="uq_document_parents_document_ordinal"
        ),
        Index("ix_document_parents_document_id", "document_id"),
        Index("ix_document_parents_knowledge_base_id", "knowledge_base_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    # 1-based source page for paginated documents (PDFs); NULL otherwise.
    page: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
