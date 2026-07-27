"""六爻 Agent 工具参数 Schema。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

DivinationToolMethod = Literal["manual", "coin", "time", "random"]


class CreateDivinationArguments(BaseModel):
    """创建并排盘工具参数。"""

    model_config = ConfigDict(extra="forbid")

    method: DivinationToolMethod
    question: str = Field(..., min_length=1, max_length=1000)
    time: datetime | None = None
    numbers: list[int] | None = None

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question 不能只包含空白字符")
        return normalized

    @model_validator(mode="after")
    def validate_method_arguments(self) -> "CreateDivinationArguments":
        if self.method in {"manual", "coin"}:
            if self.numbers is None or len(self.numbers) != 6:
                raise ValueError(
                    "manual/coin 必须提供从初爻到上爻的 6 个爻值"
                )
            if any(number not in {1, 2, 3, 4} for number in self.numbers):
                raise ValueError("爻值只能是 1、2、3、4")
        elif self.numbers is not None:
            raise ValueError("time/random 不应提供 numbers")
        return self


class GetDivinationArguments(BaseModel):
    """读取指定或当前卦例参数。"""

    model_config = ConfigDict(extra="forbid")

    divination_id: str | None = Field(
        default=None,
        min_length=32,
        max_length=32,
    )


class ListDivinationsArguments(BaseModel):
    """读取最近卦例参数。"""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=10, ge=1, le=20)
