"""游客 Session、注册与登录 API Schema。"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schema.api.user import UserResponse, _normalize_display_name

_USERNAME = re.compile(r"^[A-Za-z0-9_]+$")


def _validate_username(value: str) -> str:
    normalized = value.strip()
    if not 3 <= len(normalized) <= 32:
        raise ValueError("用户名长度必须为 3 到 32 个字符")
    if not _USERNAME.fullmatch(normalized):
        raise ValueError("用户名只能包含字母、数字和下划线")
    return normalized


class GuestSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=50)
    _normalize_name = field_validator("display_name")(_normalize_display_name)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=50)

    _normalize_username = field_validator("username")(_validate_username)
    _normalize_name = field_validator("display_name")(_normalize_display_name)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)

    _normalize_username = field_validator("username")(_validate_username)


class AuthResponse(BaseModel):
    """认证成功后返回当前用户；真实 Session Token 只写入 Cookie。"""

    user: UserResponse
