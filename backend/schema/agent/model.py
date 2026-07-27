"""Chatbot 模型适配层协议。"""
from __future__ import annotations

from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from backend.schema.agent.chat import ChatMessageType, ChatRole
from backend.schema.agent.tool import ToolDefinition


class ModelStreamEventType(str, Enum):
    """模型适配器可以产生的事件类型。"""

    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    STEP_COMPLETED = "step_completed"


class ModelFinishReason(str, Enum):
    """一次模型调用结束的原因。"""

    STOP = "stop"
    TOOL_CALLS = "tool_calls"
    LENGTH = "length"


class ModelMessage(BaseModel):
    """与具体模型供应商无关的上下文消息。"""

    model_config = ConfigDict(extra="forbid")

    role: ChatRole
    message_type: ChatMessageType = ChatMessageType.TEXT
    content: str | None = None
    tool_call_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    tool_name: str | None = Field(default=None, min_length=1, max_length=100)
    payload: JsonValue = None

    @model_validator(mode="after")
    def validate_message_shape(self) -> "ModelMessage":
        if self.message_type in {
            ChatMessageType.TEXT,
            ChatMessageType.SUMMARY,
        }:
            if self.content is None or not self.content.strip():
                raise ValueError("模型文本消息必须包含非空 content")

        if self.message_type in {
            ChatMessageType.TOOL_CALL,
            ChatMessageType.TOOL_RESULT,
        }:
            if not self.tool_call_id or not self.tool_name:
                raise ValueError(
                    "模型工具消息必须包含 tool_call_id 与 tool_name"
                )
        return self


class ModelRequest(BaseModel):
    """ReActRunner 发给模型适配器的一次完整请求。"""

    model_config = ConfigDict(extra="forbid")

    messages: list[ModelMessage] = Field(..., min_length=1)
    tools: list[ToolDefinition] = Field(default_factory=list)
    instructions: str | None = None
    model: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("instructions")
    @classmethod
    def normalize_instructions(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ModelStreamEvent(BaseModel):
    """模型适配器输出的单个流事件。"""

    model_config = ConfigDict(extra="forbid")

    event_type: ModelStreamEventType
    delta: str | None = None
    tool_call_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    tool_name: str | None = Field(default=None, min_length=1, max_length=100)
    tool_arguments: dict[str, JsonValue] | None = None
    finish_reason: ModelFinishReason | None = None

    @model_validator(mode="after")
    def validate_event_shape(self) -> "ModelStreamEvent":
        if self.event_type == ModelStreamEventType.TEXT_DELTA:
            if self.delta is None or self.delta == "":
                raise ValueError("text_delta 事件必须包含 delta")

        if self.event_type == ModelStreamEventType.TOOL_CALL:
            if not self.tool_call_id or not self.tool_name:
                raise ValueError(
                    "tool_call 事件必须包含 tool_call_id 与 tool_name"
                )
            if self.tool_arguments is None:
                raise ValueError("tool_call 事件必须包含 tool_arguments")

        if self.event_type == ModelStreamEventType.STEP_COMPLETED:
            if self.finish_reason is None:
                raise ValueError(
                    "step_completed 事件必须包含 finish_reason"
                )
        return self
