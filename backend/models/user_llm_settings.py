"""用户自带 OpenAI-compatible 模型连接。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base
from backend.models.user import utc_now

if TYPE_CHECKING:
    from backend.models.user import User


class UserLLMSettings(Base):
    """一名注册用户的一套模型连接；各角色模型为空时继承默认模型。"""

    __tablename__ = "user_llm_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    analyst_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    suggestion_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    memory_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timeout_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=120.0,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    user: Mapped["User"] = relationship(back_populates="llm_settings")
