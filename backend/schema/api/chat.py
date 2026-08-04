"""Chat 会话与消息 API Schema。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
)

ChatSessionStatus = Literal["active", "archived"]
ChatSessionOpenMode = Literal["reuse_latest", "create_new"]
ChatMessageRole = Literal["user", "assistant", "system", "tool"]
ChatMessageTypeValue = Literal[
    "text",
    "tool_call",
    "tool_result",
    "summary",
    "suggestions",
]
ChatMessageStatusValue = Literal[
    "pending",
    "completed",
    "failed",
    "cancelled",
]


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError("字段不能只包含空白字符")
    return normalized


class ChatSessionCreate(BaseModel):
    """创建聊天会话。"""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=100)
    active_divination_id: str | None = Field(
        default=None,
        min_length=32,
        max_length=32,
    )
    model: str | None = Field(default=None, min_length=1, max_length=100)

    _normalize_fields = field_validator(
        "title",
        "active_divination_id",
        "model",
    )(_normalize_optional_text)


class ChatSessionUpdate(BaseModel):
    """更新会话；显式 null 可清空可空字段。"""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=100)
    status: ChatSessionStatus | None = None
    active_divination_id: str | None = Field(
        default=None,
        min_length=32,
        max_length=32,
    )
    model: str | None = Field(default=None, min_length=1, max_length=100)

    _normalize_fields = field_validator(
        "title",
        "active_divination_id",
        "model",
    )(_normalize_optional_text)

    @field_validator("status")
    @classmethod
    def reject_null_status(
        cls,
        value: ChatSessionStatus | None,
    ) -> ChatSessionStatus:
        if value is None:
            raise ValueError("status 不能为 null")
        return value


class ChatSessionResponse(BaseModel):
    """会话响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    status: ChatSessionStatus
    active_divination_id: str | None
    summary: str | None
    summary_through_sequence: int
    summary_through_agent_message_id: int
    summary_updated_at: datetime | None
    model: str | None
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime


class ChatSessionOpenRequest(BaseModel):
    """打开卦例会话；默认复用最近会话，也可显式新建讨论。"""

    model_config = ConfigDict(extra="forbid")

    divination_id: str = Field(..., min_length=32, max_length=32)
    mode: ChatSessionOpenMode = "reuse_latest"
    title: str | None = Field(default=None, max_length=100)

    _normalize_fields = field_validator(
        "divination_id",
        "title",
    )(_normalize_optional_text)


class ChatSessionOpenResponse(BaseModel):
    """打开卦例会话的结果，并返回当前关联会话总数。"""

    created: bool
    related_session_count: int = Field(..., ge=1)
    session: ChatSessionResponse


class ChatMessageResponse(BaseModel):
    """持久化消息响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    source_message_id: uuid.UUID | None
    divination_id: str | None
    sequence: int
    role: ChatMessageRole
    message_type: ChatMessageTypeValue
    content: str | None
    tool_name: str | None
    tool_call_id: str | None
    payload: JsonValue
    status: ChatMessageStatusValue
    token_count: int | None
    created_at: datetime
    updated_at: datetime


class ChatSuggestionsResponse(BaseModel):
    """针对一条已完成助手回答生成的结构化追问。"""

    source_message_id: uuid.UUID
    questions: list[str]
    cached: bool


class ChatTurnRequest(BaseModel):
    """向会话发送一条用户消息。"""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=10000)
    model: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message 不能只包含空白字符")
        return normalized

    _normalize_model = field_validator("model")(_normalize_optional_text)
