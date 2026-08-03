"""各 Agent 模型调用的用量记录。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base
from backend.models.user import utc_now

if TYPE_CHECKING:
    from backend.models.user import User


class LLMUsageRecord(Base):
    """只保存运行元数据与 Token，不保存 Prompt、回答或密钥。"""

    __tablename__ = "llm_usage_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('completed', 'failed', 'cancelled')",
            name="valid_status",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="nonnegative_input_tokens",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="nonnegative_output_tokens",
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
    agent_role: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url_host: Mapped[str] = mapped_column(String(255), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    user: Mapped["User"] = relationship(back_populates="llm_usage_records")
