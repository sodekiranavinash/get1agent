from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from shared.models.user import User

# User-level defaults. Rows in `user_quotas` override these per user.
# Up to 10 knowledge bases x 25 files x 10 MB, capped at 100 MB storage/user.
DEFAULT_MAX_KNOWLEDGE_BASES = 10
DEFAULT_MAX_FILES_PER_KB = 25
DEFAULT_MAX_FILES_PER_USER = 250
DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_MAX_STORAGE_BYTES = 100 * 1024 * 1024  # 100 MB


class UserQuota(Base, TimestampMixin):
    __tablename__ = "user_quotas"
    __table_args__ = (
        CheckConstraint("max_file_bytes > 0", name="max_file_bytes_positive"),
        CheckConstraint("max_files_per_kb > 0", name="max_files_per_kb_positive"),
        CheckConstraint(
            "max_knowledge_bases > 0", name="max_knowledge_bases_positive"
        ),
        CheckConstraint(
            "max_files_per_user > 0", name="max_files_per_user_positive"
        ),
        CheckConstraint(
            "max_storage_bytes > 0", name="max_storage_bytes_positive"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    max_file_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("10485760"),
    )
    max_files_per_kb: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("25"),
    )
    max_knowledge_bases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("10"),
    )
    max_files_per_user: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("250"),
    )
    max_storage_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("104857600"),
    )

    user: Mapped[User] = relationship("User", back_populates="quota")
