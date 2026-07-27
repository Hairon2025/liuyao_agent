"""Chatbot Agent 内部协议。

本模块只定义 Agent、工具和上层编排之间传递的数据，不依赖 ORM、数据库、
FastAPI 或具体模型 SDK。
"""
from __future__ import annotations

import uuid
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)


class ChatRole(str, Enum):
    """上下文消息角色，与 chat_messages.role 保持一致。"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ChatMessageType(str, Enum):
    """上下文消息类型，与 chat_messages.message_type 保持一致。"""

    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SUMMARY = "summary"


class ChatMessageStatus(str, Enum):
    """上下文消息状态，与 chat_messages.status 保持一致。"""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChatEventType(str, Enum):
    """Agent 对上层发出的可观察事件。"""

    TEXT_DELTA = "text_delta"
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    TOOL_CALL_FAILED = "tool_call_failed"
    MESSAGE_COMPLETED = "message_completed"
    ERROR = "error"


class AgentProtocolModel(BaseModel):
    """所有 Agent 协议的共同配置。"""

    model_config = ConfigDict(extra="forbid")


def _normalize_optional_identifier(value: str | None) -> str | None:
    """去除可选标识符首尾空白，并拒绝只包含空白的值。"""
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError("标识符不能只包含空白字符")
    return normalized


class ChatContextMessage(AgentProtocolModel):
    """传入 Agent 的一条历史上下文消息。"""

    id: uuid.UUID
    sequence: int = Field(..., ge=1)
    role: ChatRole
    message_type: ChatMessageType = ChatMessageType.TEXT
    content: str | None = None
    tool_name: str | None = Field(default=None, min_length=1, max_length=100)
    tool_call_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    payload: JsonValue = None
    status: ChatMessageStatus = ChatMessageStatus.COMPLETED

    _normalize_identifiers = field_validator(
        "tool_name",
        "tool_call_id",
    )(_normalize_optional_identifier)

    @model_validator(mode="after")
    def validate_message_content(self) -> "ChatContextMessage":
        """文本消息必须有内容，工具消息必须能与调用记录配对。"""
        if self.message_type in {
            ChatMessageType.TEXT,
            ChatMessageType.SUMMARY,
        }:
            if self.content is None or not self.content.strip():
                raise ValueError("文本或摘要消息必须包含非空 content")

        if self.message_type in {
            ChatMessageType.TOOL_CALL,
            ChatMessageType.TOOL_RESULT,
        }:
            if not self.tool_name or not self.tool_call_id:
                raise ValueError(
                    "工具调用和工具结果必须包含 tool_name 与 tool_call_id"
                )
        return self


class ChatTurnInput(AgentProtocolModel):
    """执行一次 Chatbot 对话所需的完整输入。"""

    user_id: uuid.UUID
    session_id: uuid.UUID
    user_message: str = Field(..., min_length=1)
    session_summary: str | None = None
    summary_through_sequence: int = Field(default=0, ge=0)
    recent_messages: list[ChatContextMessage] = Field(default_factory=list)
    active_divination_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=32,
    )
    model: str | None = Field(default=None, min_length=1, max_length=100)

    _normalize_identifiers = field_validator(
        "active_divination_id",
        "model",
    )(_normalize_optional_identifier)

    @field_validator("user_message")
    @classmethod
    def normalize_user_message(cls, value: str) -> str:
        """去除首尾空白并拒绝空消息。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("user_message 不能只包含空白字符")
        return normalized

    @field_validator("session_summary")
    @classmethod
    def normalize_summary(cls, value: str | None) -> str | None:
        """空白摘要等同于尚未生成摘要。"""
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_context_window(self) -> "ChatTurnInput":
        """保证摘要游标和增量消息可以组成无歧义的上下文。"""
        if self.summary_through_sequence > 0 and self.session_summary is None:
            raise ValueError(
                "summary_through_sequence 大于 0 时必须提供 session_summary"
            )
        if self.session_summary is not None and self.summary_through_sequence == 0:
            raise ValueError(
                "提供 session_summary 时 summary_through_sequence 必须大于 0"
            )

        sequences = [message.sequence for message in self.recent_messages]
        if sequences != sorted(sequences):
            raise ValueError("recent_messages 必须按 sequence 升序排列")
        if len(sequences) != len(set(sequences)):
            raise ValueError("recent_messages 中不能包含重复 sequence")
        if any(
            sequence <= self.summary_through_sequence
            for sequence in sequences
        ):
            raise ValueError(
                "recent_messages 必须位于 summary_through_sequence 之后"
            )
        return self


class ToolContext(AgentProtocolModel):
    """系统注入给工具的身份与会话上下文。

    这些字段不能成为模型可自行填写的工具参数。
    """

    user_id: uuid.UUID
    session_id: uuid.UUID
    tool_call_id: str = Field(..., min_length=1, max_length=100)
    active_divination_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=32,
    )

    _normalize_identifiers = field_validator(
        "tool_call_id",
        "active_divination_id",
    )(_normalize_optional_identifier)


class ToolResult(AgentProtocolModel):
    """工具执行后的标准结果。"""

    success: bool
    # 提供给模型作为 Observation，成功和失败时都必须可读。
    model_content: str = Field(..., min_length=1)
    # 可选的用户界面简短说明，避免直接展示冗长模型上下文。
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
    """Agent 流式执行过程中发出的统一事件。"""

    event_type: ChatEventType
    # text_delta 为文本增量，message_completed 为完整最终文本，error 为错误说明。
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

    _normalize_identifiers = field_validator(
        "tool_call_id",
        "tool_name",
        "error_code",
    )(_normalize_optional_identifier)

    @model_validator(mode="after")
    def validate_event_payload(self) -> "ChatEvent":
        """根据事件类型检查必要字段及工具结果状态。"""
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
