from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from shared.models.user import User

# User-level defaults. Rows in `user_quotas` override these per user.
# Up to 20 knowledge bases x 20 files x 20 MB, capped at 200 MB storage/user.
DEFAULT_MAX_KNOWLEDGE_BASES = 20
DEFAULT_MAX_FILES_PER_KB = 20
DEFAULT_MAX_FILES_PER_USER = 400
DEFAULT_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB
DEFAULT_MAX_STORAGE_BYTES = 200 * 1024 * 1024  # 200 MB


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
        server_default=text("20971520"),
    )
    max_files_per_kb: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("20"),
    )
    max_knowledge_bases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("20"),
    )
    max_files_per_user: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("400"),
    )
    max_storage_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("209715200"),
    )

    user: Mapped[User] = relationship("User", back_populates="quota")
