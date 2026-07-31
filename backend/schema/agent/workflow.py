"""Chatbot 领域工作流状态与结果 Schema。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schema.api.divination import QiguaMethod

CoinFace = Literal["字", "花"]
DivinationTimeMode = Literal["now", "specified"]


class DivinationDraft(BaseModel):
    """一次尚未完成的起卦信息草稿。"""

    model_config = ConfigDict(extra="forbid")

    question: str | None = Field(default=None, max_length=1000)
    method: QiguaMethod | None = None
    time_mode: DivinationTimeMode | None = None
    time: datetime | None = None
    numbers: list[int] | None = None
    coin_tosses: list[list[CoinFace]] = Field(default_factory=list)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ChatWorkflowState(BaseModel):
    """保存在 ``chat_sessions.workflow_state`` 中的版本化状态。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["divination"] = "divination"
    version: Literal[2] = 2
    status: Literal["collecting"] = "collecting"
    payload: DivinationDraft = Field(default_factory=DivinationDraft)


class DivinationWorkflowOutcome(BaseModel):
    """多轮起卦工作流返回给 Function Tool 的结构化结果。"""

    model_config = ConfigDict(extra="forbid")

    status: Literal["needs_input", "created"]
    missing_fields: list[str] = Field(default_factory=list)
    draft: DivinationDraft | None = None
    divination_id: str | None = None
    hexagram_name: str | None = None
    qigua_time: datetime | None = None
    paipan_markdown: str | None = None
