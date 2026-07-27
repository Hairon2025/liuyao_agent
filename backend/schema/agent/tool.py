"""Agent 工具描述协议。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class ToolDefinition(BaseModel):
    """提供给模型适配层的工具元数据和 JSON Schema。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    description: str = Field(..., min_length=1)
    parameters: dict[str, JsonValue]

    @field_validator("name", "description")
    @classmethod
    def strip_nonblank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("工具名称和说明不能只包含空白字符")
        return normalized
