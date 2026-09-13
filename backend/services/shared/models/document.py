from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from shared.models.document_tag import DocumentTag
    from shared.models.knowledge_base import KnowledgeBase
    from shared.models.user import User

DOCUMENT_SOURCES = ("upload", "inline")
DOCUMENT_STATUSES = ("pending", "uploaded", "processing", "ready", "failed")


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "source IN ('upload', 'inline')",
            name="source_valid",
        ),
        CheckConstraint(
            "status IN ('pending', 'uploaded', 'processing', 'ready', 'failed')",
            name="status_valid",
        ),
        CheckConstraint("size_bytes >= 0", name="size_bytes_non_negative"),
        UniqueConstraint("knowledge_base_id", "file_name"),
        Index("ix_documents_knowledge_base_id", "knowledge_base_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
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
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    s3_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'pending'"),
    )
    embed_model: Mapped[str | None] = mapped_column(String(128))
    image_embed_model: Mapped[str | None] = mapped_column(String(128))
    chunk_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    image_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    knowledge_base: Mapped[KnowledgeBase] = relationship(
        "KnowledgeBase",
        back_populates="documents",
    )
    user: Mapped[User] = relationship("User", back_populates="documents")
    tags: Mapped[list[DocumentTag]] = relationship(
        "DocumentTag",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentTag.created_at",
    )
