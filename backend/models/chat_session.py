"""聊天会话 ORM Model。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base
from backend.models.user import utc_now

if TYPE_CHECKING:
    from backend.models.chat_message import ChatMessage
    from backend.models.divination import Divination
    from backend.models.user import User


class ChatSession(Base):
    """用户与 Chatbot 的一次连续会话。

    `summary` 和 `summary_through_sequence` 是旧版自研上下文摘要的兼容字段，
    Agents SDK 运行时不再读取它们；
    `active_divination_id` 只表示当前主要讨论的卦例，不限制会话关联多个卦例。
    """

    __tablename__ = "chat_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="valid_status",
        ),
        CheckConstraint(
            "summary_through_sequence >= 0",
            name="nonnegative_summary_sequence",
        ),
        CheckConstraint(
            "next_message_sequence > 0",
            name="positive_next_message_sequence",
        ),
        Index(
            "ix_chat_sessions_user_last_message_at",
            "user_id",
            "last_message_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
    )
    active_divination_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("divinations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 显式保存尚未完成的领域工作流，避免关键参数只存在于模型上下文中。
    workflow_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    # 兼容旧数据库/API；模型上下文已由 agent_messages 管理。
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_through_sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    # Repository 通过原子 UPDATE 预留序号，避免并发写入时 MAX(sequence)+1 冲突。
    next_message_sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
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
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    user: Mapped["User"] = relationship(back_populates="chat_sessions")
    active_divination: Mapped["Divination | None"] = relationship(
        back_populates="active_chat_sessions",
        foreign_keys=[active_divination_id],
    )
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ChatMessage.sequence",
    )
