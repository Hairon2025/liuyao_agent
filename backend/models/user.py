"""用户 ORM Model。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


def utc_now() -> datetime:
    """返回带时区的 UTC 时间，便于未来迁移到 PostgreSQL。"""
    return datetime.now(timezone.utc)


class User(Base):
    """系统用户。

    第一阶段只创建 guest 用户；registered 类型为后续登录注册预留。
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
