"""前端流式事件与业务工具结果协议。

模型消息、工具定义和运行上下文由 OpenAI Agents SDK 负责；这里只保留
本项目 API 层需要长期稳定的事件格式。
"""
from __future__ import annotations

from enum import Enum
import uuid

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)


class ChatEventType(str, Enum):
    """Agent 对 API 层发出的可观察事件。"""

    RUN_STARTED = "run_started"
    TEXT_DELTA = "text_delta"
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    TOOL_CALL_FAILED = "tool_call_failed"
    MESSAGE_COMPLETED = "message_completed"
    SUGGESTIONS = "suggestions"
    ERROR = "error"


class AgentProtocolModel(BaseModel):
    """项目内部事件协议的共同配置。"""

    model_config = ConfigDict(extra="forbid")


def _normalize_optional_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError("标识符不能只包含空白字符")
    return normalized


class ToolResult(AgentProtocolModel):
    """Function Tool 返回给模型和界面的统一业务结果。"""

    success: bool
    model_content: str = Field(..., min_length=1)
    display_content: str | None = None
    data: JsonValue = None
    error_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    retryable: bool = False

    _normalize_error_code = field_validator(
        "error_code",
    )(_normalize_optional_identifier)

    @field_validator("model_content")
    @classmethod
    def reject_blank_model_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model_content 不能只包含空白字符")
        return value

    @model_validator(mode="after")
    def validate_error_state(self) -> "ToolResult":
        if self.success and self.error_code is not None:
            raise ValueError("成功的 ToolResult 不能包含 error_code")
        if not self.success and self.error_code is None:
            raise ValueError("失败的 ToolResult 必须包含 error_code")
        return self


class ChatEvent(AgentProtocolModel):
    """把 SDK 事件适配成现有 SSE 接口使用的统一事件。"""

    event_type: ChatEventType
    request_id: uuid.UUID | None = None
    content: str | None = None
    tool_call_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    tool_name: str | None = Field(default=None, min_length=1, max_length=100)
    tool_arguments: JsonValue = None
    tool_result: ToolResult | None = None
    error_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    retryable: bool = False
    message_id: uuid.UUID | None = None
    source_message_id: uuid.UUID | None = None
    questions: list[str] | None = None

    _normalize_identifiers = field_validator(
        "tool_call_id",
        "tool_name",
        "error_code",
    )(_normalize_optional_identifier)

    @model_validator(mode="after")
    def validate_event_payload(self) -> "ChatEvent":
        if (
            self.event_type == ChatEventType.RUN_STARTED
            and self.request_id is None
        ):
            raise ValueError("run_started 事件必须包含 request_id")

        if self.event_type in {
            ChatEventType.TEXT_DELTA,
            ChatEventType.MESSAGE_COMPLETED,
        }:
            if self.content is None or self.content == "":
                raise ValueError(f"{self.event_type.value} 必须包含 content")

        if self.event_type == ChatEventType.ERROR:
            if self.content is None or not self.content.strip():
                raise ValueError("error 事件必须包含错误说明")
            if self.error_code is None:
                raise ValueError("error 事件必须包含 error_code")

        if self.event_type == ChatEventType.SUGGESTIONS:
            if self.source_message_id is None:
                raise ValueError("suggestions 事件必须包含 source_message_id")
            if self.questions is None or len(self.questions) != 3:
                raise ValueError("suggestions 事件必须包含三条追问")

        if self.event_type in {
            ChatEventType.TOOL_CALL_STARTED,
            ChatEventType.TOOL_CALL_COMPLETED,
            ChatEventType.TOOL_CALL_FAILED,
        }:
            if not self.tool_call_id or not self.tool_name:
                raise ValueError(
                    "工具事件必须包含 tool_call_id 与 tool_name"
                )

        if self.event_type == ChatEventType.TOOL_CALL_COMPLETED:
            if self.tool_result is None or not self.tool_result.success:
                raise ValueError(
                    "tool_call_completed 必须包含成功的 tool_result"
                )

        if self.event_type == ChatEventType.TOOL_CALL_FAILED:
            if self.tool_result is None or self.tool_result.success:
                raise ValueError(
                    "tool_call_failed 必须包含失败的 tool_result"
                )
        return self
