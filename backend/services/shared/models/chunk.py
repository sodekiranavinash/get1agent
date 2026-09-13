from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from shared.models.base import Base, TimestampMixin
from shared.models.types import Vector

if TYPE_CHECKING:
    from shared.models.document import Document
    from shared.models.knowledge_base import KnowledgeBase
    from shared.models.user import User

EMBEDDING_DIM = 1024


class Chunk(Base, TimestampMixin):
    """A text chunk of a document and its embedding (Titan Text V2)."""

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_hash"),
        Index("ix_chunks_document_id", "document_id"),
        Index("ix_chunks_knowledge_base_id", "knowledge_base_id"),
        Index("ix_chunks_parent_id", "parent_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The larger context unit (page/section) this child belongs to. NULL only
    # for documents indexed before parent-document retrieval existed.
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("document_parents.id", ondelete="CASCADE"),
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
    chunk_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    # 1-based source page range for paginated documents (PDFs); NULL otherwise.
    # Retrieval uses these to cite "page N" and deep-link into the PDF.
    page: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
