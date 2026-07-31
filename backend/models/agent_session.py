"""OpenAI Agents SDK SQLAlchemySession 使用的 ORM 表。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class AgentSessionRecord(Base):
    """SDK 会话元数据。

    表结构与 ``agents.extensions.memory.SQLAlchemySession`` 保持一致。
    业务所有权仍由 ``chat_sessions`` 管理，使用前必须先校验用户身份。
    """

    __tablename__ = "agent_sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )


class AgentMessageRecord(Base):
    """SDK 持久化的一条模型输入或输出 Item。"""

    __tablename__ = "agent_messages"
    __table_args__ = (
        Index(
            "idx_agent_messages_session_time",
            "session_id",
            "created_at",
        ),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("agent_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    message_data: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
