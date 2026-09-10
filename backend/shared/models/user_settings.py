from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from shared.models.user import User

THEMES = ("light", "dark")


class UserSettings(Base, TimestampMixin):
    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint(
            "preferred_theme IN ('light', 'dark')",
            name="preferred_theme_valid",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    preferred_theme: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'dark'"),
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'UTC'"),
    )

    user: Mapped[User] = relationship("User", back_populates="settings")
