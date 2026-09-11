from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from shared.models.document import Document
    from shared.models.user import User

KNOWLEDGE_BASE_STATUSES = ("processing", "ready", "failed")


class KnowledgeBase(Base, TimestampMixin):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('processing', 'ready', 'failed')",
            name="status_valid",
        ),
        Index("ix_knowledge_bases_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'ready'"),
    )

    user: Mapped[User] = relationship("User", back_populates="knowledge_bases")
    documents: Mapped[list[Document]] = relationship(
        "Document",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
        order_by="Document.created_at",
    )
