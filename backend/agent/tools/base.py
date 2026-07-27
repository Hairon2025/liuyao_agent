"""Agent 工具基础接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from backend.schema.agent import ToolContext, ToolDefinition, ToolResult

ArgumentsT = TypeVar("ArgumentsT", bound=BaseModel)


class ToolArgumentsError(ValueError):
    """模型提供的工具参数无法通过 Schema 校验。"""

    def __init__(
        self,
        tool_name: str,
        errors: list[dict[str, Any]],
    ):
        self.tool_name = tool_name
        self.errors = errors
        super().__init__(f"工具 {tool_name} 的参数校验失败")


class AgentTool(ABC, Generic[ArgumentsT]):
    """所有 Chatbot 工具的共同抽象。

    工具只接收经过校验的业务参数和系统注入的 ToolContext，不接触模型原始
    响应格式。具体模型 SDK 的工具描述转换由后续模型适配层负责。
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        arguments_schema: type[ArgumentsT],
    ):
        if not isinstance(arguments_schema, type) or not issubclass(
            arguments_schema,
            BaseModel,
        ):
            raise TypeError("arguments_schema 必须是 Pydantic BaseModel 子类")
        if arguments_schema.model_config.get("extra") != "forbid":
            raise ValueError(
                "工具参数 Schema 必须设置 ConfigDict(extra='forbid')"
            )

        self._arguments_schema = arguments_schema
        self._definition = ToolDefinition(
            name=name,
            description=description,
            parameters=arguments_schema.model_json_schema(),
        )

    @property
    def name(self) -> str:
        return self._definition.name

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def arguments_schema(self) -> type[ArgumentsT]:
        return self._arguments_schema

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def parse_arguments(
        self,
        raw_arguments: Mapping[str, Any] | None,
    ) -> ArgumentsT:
        """把模型产生的 JSON 对象转换为工具专用参数模型。"""
        if raw_arguments is None:
            payload: dict[str, Any] = {}
        elif isinstance(raw_arguments, Mapping):
            payload = dict(raw_arguments)
        else:
            raise ToolArgumentsError(
                self.name,
                [
                    {
                        "type": "mapping_type",
                        "loc": (),
                        "msg": "工具参数必须是 JSON 对象",
                        "input": raw_arguments,
                    }
                ],
            )

        try:
            return self._arguments_schema.model_validate(payload)
        except ValidationError as exc:
            raise ToolArgumentsError(
                self.name,
                exc.errors(),
            ) from exc

    async def run(
        self,
        context: ToolContext,
        raw_arguments: Mapping[str, Any] | None,
    ) -> ToolResult:
        """校验参数后执行工具，并检查实现是否遵守返回协议。"""
        arguments = self.parse_arguments(raw_arguments)
        result = await self.execute(context, arguments)
        if not isinstance(result, ToolResult):
            raise TypeError(
                f"工具 {self.name}.execute() 必须返回 ToolResult"
            )
        return result

    @abstractmethod
    async def execute(
        self,
        context: ToolContext,
        arguments: ArgumentsT,
    ) -> ToolResult:
        """执行工具业务逻辑。"""
        raise NotImplementedError
