"""用户 ORM Model。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base

if TYPE_CHECKING:
    from backend.models.chat_session import ChatSession
    from backend.models.divination import Divination
    from backend.models.auth import AuthSession, UserCredential
    from backend.models.llm_usage import LLMUsageRecord
    from backend.models.user_llm_settings import UserLLMSettings


def utc_now() -> datetime:
    """返回带时区的 UTC 时间，便于未来迁移到 PostgreSQL。"""
    return datetime.now(timezone.utc)


class User(Base):
    """系统用户。

    guest 没有用户名和密码；注册时在原记录上升级，保留已有卦例与会话。
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "user_type IN ('guest', 'registered')",
            name="valid_user_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="guest",
        index=True,
    )
    username: Mapped[str | None] = mapped_column(String(32), nullable=True)
    username_normalized: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        unique=True,
        index=True,
    )
    display_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
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
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    divinations: Mapped[list["Divination"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    credential: Mapped["UserCredential | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    auth_sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    llm_settings: Mapped["UserLLMSettings | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    llm_usage_records: Mapped[list["LLMUsageRecord"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
