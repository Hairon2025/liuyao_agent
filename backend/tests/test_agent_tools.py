"""AgentTool 与 ToolRegistry 单元测试。"""
from __future__ import annotations

import uuid

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.agent.tools import (
    AgentTool,
    DuplicateToolError,
    ToolArgumentsError,
    ToolNotFoundError,
    ToolRegistry,
)
from backend.schema.agent import ToolContext, ToolResult


class EchoArguments(BaseModel):
    """Fake Tool 参数。"""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    repeat: int = Field(default=1, ge=1, le=3)


class EchoTool(AgentTool[EchoArguments]):
    """记录调用信息的 Fake Tool。"""

    def __init__(self, name: str = "echo"):
        super().__init__(
            name=name,
            description="重复返回指定文本",
            arguments_schema=EchoArguments,
        )
        self.calls: list[tuple[ToolContext, EchoArguments]] = []

    async def execute(
        self,
        context: ToolContext,
        arguments: EchoArguments,
    ) -> ToolResult:
        self.calls.append((context, arguments))
        content = arguments.text * arguments.repeat
        return ToolResult(
            success=True,
            model_content=content,
            display_content=content,
            data={"length": len(content)},
        )


class InvalidReturnTool(EchoTool):
    """故意违反返回协议的 Fake Tool。"""

    async def execute(self, context, arguments):  # type: ignore[override]
        return {"content": arguments.text}


def _tool_context() -> ToolContext:
    return ToolContext(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        tool_call_id="call-001",
    )


def test_agent_tool_exposes_provider_neutral_definition():
    tool = EchoTool()

    assert tool.name == "echo"
    assert tool.description == "重复返回指定文本"
    assert tool.arguments_schema is EchoArguments
    assert tool.definition.name == "echo"
    assert tool.definition.parameters["type"] == "object"
    assert set(tool.definition.parameters["properties"]) == {
        "text",
        "repeat",
    }

    dumped = tool.definition.model_dump(mode="json")
    assert dumped["parameters"]["required"] == ["text"]


@pytest.mark.asyncio
async def test_agent_tool_validates_arguments_before_execution():
    tool = EchoTool()
    context = _tool_context()

    result = await tool.run(
        context,
        {"text": "易", "repeat": 2},
    )

    assert result.success is True
    assert result.model_content == "易易"
    assert result.data == {"length": 2}
    assert len(tool.calls) == 1
    assert tool.calls[0][0] == context
    assert tool.calls[0][1] == EchoArguments(text="易", repeat=2)

    with pytest.raises(ToolArgumentsError) as exc_info:
        await tool.run(
            context,
            {"text": "错误参数", "unknown": True},
        )

    assert exc_info.value.tool_name == "echo"
    assert exc_info.value.errors
    # 参数失败时不应进入 execute。
    assert len(tool.calls) == 1


def test_agent_tool_rejects_non_object_arguments():
    tool = EchoTool()

    with pytest.raises(ToolArgumentsError, match="参数校验失败") as exc_info:
        tool.parse_arguments(["not", "an", "object"])  # type: ignore[arg-type]

    assert exc_info.value.errors[0]["type"] == "mapping_type"


@pytest.mark.asyncio
async def test_agent_tool_checks_implementation_return_type():
    tool = InvalidReturnTool(name="invalid_return")

    with pytest.raises(TypeError, match="必须返回 ToolResult"):
        await tool.run(_tool_context(), {"text": "测试"})


def test_agent_tool_rejects_invalid_metadata_and_loose_argument_schema():
    with pytest.raises(ValidationError):
        EchoTool(name="Invalid-Tool-Name")

    class LooseArguments(BaseModel):
        value: str

    class LooseTool(AgentTool[LooseArguments]):
        async def execute(self, context, arguments):
            return ToolResult(success=True, model_content=arguments.value)

    with pytest.raises(ValueError, match="extra='forbid'"):
        LooseTool(
            name="loose",
            description="不严格的参数模型",
            arguments_schema=LooseArguments,
        )


@pytest.mark.asyncio
async def test_registry_preserves_order_and_dispatches_registered_tool():
    first = EchoTool("first_echo")
    second = EchoTool("second_echo")
    registry = ToolRegistry([first])
    registry.register(second)

    assert len(registry) == 2
    assert "first_echo" in registry
    assert registry.names() == ("first_echo", "second_echo")
    assert list(registry) == [first, second]
    assert registry.get("first_echo") is first
    assert registry.get_optional("missing") is None
    assert tuple(item.name for item in registry.definitions()) == (
        "first_echo",
        "second_echo",
    )

    result = await registry.execute(
        "second_echo",
        _tool_context(),
        {"text": "爻", "repeat": 3},
    )
    assert result.model_content == "爻爻爻"
    assert len(second.calls) == 1
    assert first.calls == []


def test_registry_rejects_duplicate_unknown_and_non_tool_values():
    registry = ToolRegistry([EchoTool()])

    with pytest.raises(DuplicateToolError, match="已注册"):
        registry.register(EchoTool())

    with pytest.raises(ToolNotFoundError, match="未注册"):
        registry.get("missing")

    with pytest.raises(TypeError, match="AgentTool"):
        registry.register(object())  # type: ignore[arg-type]
