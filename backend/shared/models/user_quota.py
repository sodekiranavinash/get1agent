from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from shared.models.user import User

# User-level defaults. Rows in `user_quotas` override these per user.
DEFAULT_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_MAX_FILES_PER_KB = 10


class UserQuota(Base, TimestampMixin):
    __tablename__ = "user_quotas"
    __table_args__ = (
        CheckConstraint("max_file_bytes > 0", name="max_file_bytes_positive"),
        CheckConstraint("max_files_per_kb > 0", name="max_files_per_kb_positive"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    max_file_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("52428800"),
    )
    max_files_per_kb: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("10"),
    )

    user: Mapped[User] = relationship("User", back_populates="quota")
