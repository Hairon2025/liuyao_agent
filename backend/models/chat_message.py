"""聊天消息 ORM Model。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base
from backend.models.user import utc_now

if TYPE_CHECKING:
    from backend.models.chat_session import ChatSession
    from backend.models.divination import Divination


class ChatMessage(Base):
    """会话中的一条消息或一次可观察的工具事件。

    ReAct 的隐藏思维过程不入库；只保存用户可见文本、工具调用参数及结果。
    """

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name="valid_role",
        ),
        CheckConstraint(
            "message_type IN "
            "('text', 'tool_call', 'tool_result', 'summary', 'suggestions')",
            name="valid_message_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed', 'cancelled')",
            name="valid_status",
        ),
        CheckConstraint(
            "sequence > 0",
            name="positive_sequence",
        ),
        CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name="nonnegative_token_count",
        ),
        UniqueConstraint(
            "session_id",
            "sequence",
            name="uq_chat_messages_session_sequence",
        ),
        UniqueConstraint(
            "source_message_id",
            name="uq_chat_messages_source_message_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=True,
    )
    divination_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("divinations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    message_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="text",
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    payload: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="completed",
    )
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
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

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
    divination: Mapped["Divination | None"] = relationship(
        back_populates="chat_messages",
    )
