"""User API 的请求与响应 Schema。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

UserType = Literal["guest", "registered"]


def _normalize_display_name(value: str | None) -> str | None:
    """去除昵称首尾空白，并拒绝仅包含空白字符的昵称。"""
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError("昵称不能只包含空白字符")
    return normalized


class UserCreate(BaseModel):
    """创建匿名用户请求。"""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=50)

    _normalize_name = field_validator("display_name")(_normalize_display_name)


class UserUpdate(BaseModel):
    """更新用户资料请求。

    display_name 显式传 null 表示清空昵称；完全不传表示不修改。
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=50)
    _normalize_name = field_validator("display_name")(_normalize_display_name)


class UserResponse(BaseModel):
    """用户对外响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_type: UserType
    display_name: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
