"""卦例 ORM Model。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base
from backend.models.user import utc_now

if TYPE_CHECKING:
    from backend.models.user import User


class Divination(Base):
    """持久化一次完整卦例。

    排盘和解读保留结构化 JSON，便于保持现有 API 响应兼容；
    常用检索字段单独成列，后续做会话关联和历史搜索时无需扫描 JSON。
    """

    __tablename__ = "divinations"
    __table_args__ = (
        Index(
            "ix_divinations_user_created_at",
            "user_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    qigua_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    numbers: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    paipan: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    interpretation: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    markdown_content: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    user: Mapped["User"] = relationship(back_populates="divinations")
