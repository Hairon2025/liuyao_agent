"""Agent 工具注册表。"""
from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from backend.agent.tools.base import AgentTool
from backend.schema.agent import ToolContext, ToolDefinition, ToolResult


class DuplicateToolError(ValueError):
    """注册了重复名称的工具。"""


class ToolNotFoundError(LookupError):
    """请求了未注册的工具。"""


class ToolRegistry:
    """管理当前 Chatbot 允许模型调用的工具集合。

    注册顺序会被保留，便于模型适配层生成稳定的工具描述列表。
    """

    def __init__(
        self,
        tools: Iterable[AgentTool[Any]] | None = None,
    ):
        self._tools: dict[str, AgentTool[Any]] = {}
        for tool in tools or ():
            self.register(tool)

    def register(self, tool: AgentTool[Any]) -> AgentTool[Any]:
        """注册工具；重复名称直接报错，避免静默覆盖实现。"""
        if not isinstance(tool, AgentTool):
            raise TypeError("ToolRegistry 只能注册 AgentTool 实例")
        if tool.name in self._tools:
            raise DuplicateToolError(f"工具 {tool.name} 已注册")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> AgentTool[Any]:
        """按名称获取工具，不存在时抛出明确异常。"""
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(f"工具 {name} 未注册") from None

    def get_optional(self, name: str) -> AgentTool[Any] | None:
        """按名称获取工具，不存在时返回 None。"""
        return self._tools.get(name)

    def definitions(self) -> tuple[ToolDefinition, ...]:
        """返回稳定且不可直接增删的工具描述序列。"""
        return tuple(tool.definition for tool in self._tools.values())

    def names(self) -> tuple[str, ...]:
        """按注册顺序返回工具名称。"""
        return tuple(self._tools)

    async def execute(
        self,
        name: str,
        context: ToolContext,
        raw_arguments: Mapping[str, Any] | None,
    ) -> ToolResult:
        """查找并执行指定工具。"""
        return await self.get(name).run(context, raw_arguments)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __iter__(self) -> Iterator[AgentTool[Any]]:
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)
