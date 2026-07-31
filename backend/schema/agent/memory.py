"""Chatbot 长期记忆的结构化协议。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationMemory(BaseModel):
    """摘要 Agent 输出并持久化的长期记忆。"""

    model_config = ConfigDict(extra="forbid")

    current_focus: str | None = Field(default=None, max_length=300)
    user_context: list[str] = Field(default_factory=list, max_length=12)
    user_preferences: list[str] = Field(default_factory=list, max_length=10)
    divination_context: list[str] = Field(default_factory=list, max_length=12)
    key_conclusions: list[str] = Field(default_factory=list, max_length=16)
    unresolved_questions: list[str] = Field(
        default_factory=list,
        max_length=10,
    )

    @field_validator(
        "user_context",
        "user_preferences",
        "divination_context",
        "key_conclusions",
        "unresolved_questions",
    )
    @classmethod
    def normalize_items(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            item = value.strip()
            if not item or item in normalized:
                continue
            if len(item) > 300:
                raise ValueError("长期记忆的单条内容不能超过 300 个字符")
            normalized.append(item)
        return normalized
