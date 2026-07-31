"""追问建议 Agent 的结构化输出。"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SuggestedQuestions(BaseModel):
    """模型生成的追问建议。

    与当前回答无关时允许返回空数组；需要展示时必须一次返回三条，避免前端
    出现数量忽多忽少的布局。
    """

    model_config = ConfigDict(extra="forbid")

    questions: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("questions")
    @classmethod
    def normalize_questions(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(set(normalized)) != len(normalized):
            raise ValueError("追问建议不能重复")
        if any(len(value) > 80 for value in normalized):
            raise ValueError("单条追问建议不能超过 80 个字符")
        return normalized

    @model_validator(mode="after")
    def validate_question_count(self) -> "SuggestedQuestions":
        if self.questions and len(self.questions) != 3:
            raise ValueError("追问建议必须为空或恰好三条")
        return self


class SuggestedQuestionsPayload(SuggestedQuestions):
    """保存到 chat_messages.payload 并发给前端的稳定结构。"""

    source_message_id: uuid.UUID

