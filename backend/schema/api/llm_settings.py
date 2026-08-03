"""用户自带 LLM 连接的对外 Schema。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class UserLLMSettingsUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(..., min_length=1, max_length=500)
    api_key: str | None = Field(default=None, min_length=1, max_length=1000)
    model: str = Field(..., min_length=1, max_length=100)
    analyst_model: str | None = Field(default=None, max_length=100)
    suggestion_model: str | None = Field(default=None, max_length=100)
    memory_model: str | None = Field(default=None, max_length=100)
    timeout_seconds: float = Field(default=120.0, ge=10, le=300)

    _normalize_optional_models = field_validator(
        "analyst_model",
        "suggestion_model",
        "memory_model",
    )(_strip_optional)

    @field_validator("base_url", "model", "api_key")
    @classmethod
    def normalize_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("该字段不能为空白字符")
        return normalized


class UserLLMSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_url: str
    api_key_configured: bool = True
    api_key_last4: str
    model: str
    analyst_model: str | None
    suggestion_model: str | None
    memory_model: str | None
    timeout_seconds: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LLMConnectionTestResponse(BaseModel):
    success: bool
    message: str
