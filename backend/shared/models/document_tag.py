from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from shared.models.document import Document

MIN_TAG_DESCRIPTION_LENGTH = 30
MAX_TAGS_PER_DOCUMENT = 10


class DocumentTag(Base, TimestampMixin):
    __tablename__ = "document_tags"
    __table_args__ = (
        UniqueConstraint("document_id", "name"),
        CheckConstraint(
            "char_length(description) >= 30",
            name="description_min_length",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    document: Mapped[Document] = relationship("Document", back_populates="tags")
