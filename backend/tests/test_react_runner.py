"""最小 ReActRunner 单元测试。"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from pydantic import BaseModel, ConfigDict, Field

from backend.agent.model import ChatModelAdapter
from backend.agent.react_runner import ReActRunner
from backend.agent.tools import AgentTool, ToolRegistry
from backend.schema.agent import (
    ChatContextMessage,
    ChatEventType,
    ChatMessageType,
    ChatRole,
    ChatTurnInput,
    ModelFinishReason,
    ModelRequest,
    ModelStreamEvent,
    ModelStreamEventType,
    ToolContext,
    ToolResult,
)


class EchoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)


class EchoTool(AgentTool[EchoArguments]):
    def __init__(self):
        super().__init__(
            name="echo",
            description="返回指定文本",
            arguments_schema=EchoArguments,
        )
        self.contexts: list[ToolContext] = []

    async def execute(
        self,
        context: ToolContext,
        arguments: EchoArguments,
    ) -> ToolResult:
        self.contexts.append(context)
        return ToolResult(
            success=True,
            model_content=f"工具返回：{arguments.text}",
            data={"text": arguments.text},
        )


class SelectDivinationTool(AgentTool[EchoArguments]):
    def __init__(self):
        super().__init__(
            name="select_divination",
            description="选择卦例",
            arguments_schema=EchoArguments,
        )

    async def execute(
        self,
        context: ToolContext,
        arguments: EchoArguments,
    ) -> ToolResult:
        return ToolResult(
            success=True,
            model_content="已选择",
            data={"divination_id": "b" * 32},
        )


class FakeModelAdapter(ChatModelAdapter):
    """每次模型调用依次返回预设事件。"""

    def __init__(self, steps: list[list[ModelStreamEvent] | Exception]):
        self._steps = list(steps)
        self.requests: list[ModelRequest] = []

    def stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        step = self._steps.pop(0)

        async def generate() -> AsyncIterator[ModelStreamEvent]:
            if isinstance(step, Exception):
                raise step
            for event in step:
                yield event

        return generate()


def _turn_input() -> ChatTurnInput:
    return ChatTurnInput(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        user_message="继续分析",
        session_summary="此前已经完成排盘",
        summary_through_sequence=1,
        recent_messages=[
            ChatContextMessage(
                id=uuid.uuid4(),
                sequence=2,
                role=ChatRole.ASSISTANT,
                content="请问还想了解什么？",
            )
        ],
        active_divination_id="a" * 32,
        model="fake-model",
    )


async def _collect(runner: ReActRunner, turn_input: ChatTurnInput):
    return [event async for event in runner.run(turn_input)]


@pytest.mark.asyncio
async def test_runner_streams_text_and_emits_full_completed_message():
    adapter = FakeModelAdapter(
        [
            [
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TEXT_DELTA,
                    delta="世爻",
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TEXT_DELTA,
                    delta="较旺。",
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.STEP_COMPLETED,
                    finish_reason=ModelFinishReason.STOP,
                ),
            ]
        ]
    )
    runner = ReActRunner(
        model_adapter=adapter,
        tool_registry=ToolRegistry(),
        instructions="你是六爻助手。",
    )

    events = await _collect(runner, _turn_input())

    assert [event.event_type for event in events] == [
        ChatEventType.TEXT_DELTA,
        ChatEventType.TEXT_DELTA,
        ChatEventType.MESSAGE_COMPLETED,
    ]
    assert events[-1].content == "世爻较旺。"
    request = adapter.requests[0]
    assert request.instructions == "你是六爻助手。"
    assert request.model == "fake-model"
    assert [message.role for message in request.messages] == [
        ChatRole.SYSTEM,
        ChatRole.ASSISTANT,
        ChatRole.USER,
    ]


@pytest.mark.asyncio
async def test_runner_executes_tool_and_returns_observation_to_model():
    tool = EchoTool()
    adapter = FakeModelAdapter(
        [
            [
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TOOL_CALL,
                    tool_call_id="call-1",
                    tool_name="echo",
                    tool_arguments={"text": "卦象信息"},
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.STEP_COMPLETED,
                    finish_reason=ModelFinishReason.TOOL_CALLS,
                ),
            ],
            [
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TEXT_DELTA,
                    delta="根据工具结果，整体平稳。",
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.STEP_COMPLETED,
                    finish_reason=ModelFinishReason.STOP,
                ),
            ],
        ]
    )
    turn_input = _turn_input()
    runner = ReActRunner(
        model_adapter=adapter,
        tool_registry=ToolRegistry([tool]),
    )

    events = await _collect(runner, turn_input)

    assert [event.event_type for event in events] == [
        ChatEventType.TOOL_CALL_STARTED,
        ChatEventType.TOOL_CALL_COMPLETED,
        ChatEventType.TEXT_DELTA,
        ChatEventType.MESSAGE_COMPLETED,
    ]
    assert len(tool.contexts) == 1
    assert tool.contexts[0].user_id == turn_input.user_id
    assert tool.contexts[0].session_id == turn_input.session_id
    assert tool.contexts[0].active_divination_id == "a" * 32

    second_request = adapter.requests[1]
    assert second_request.messages[-2].tool_call_id == "call-1"
    assert second_request.messages[-1].content == "工具返回：卦象信息"
    assert second_request.messages[-1].role == ChatRole.TOOL


@pytest.mark.asyncio
async def test_runner_completed_message_includes_text_before_tool_call():
    adapter = FakeModelAdapter(
        [
            [
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TEXT_DELTA,
                    delta="我先查一下。",
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TOOL_CALL,
                    tool_call_id="call-preface",
                    tool_name="echo",
                    tool_arguments={"text": "排盘"},
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.STEP_COMPLETED,
                    finish_reason=ModelFinishReason.TOOL_CALLS,
                ),
            ],
            [
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TEXT_DELTA,
                    delta="结果整体平稳。",
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.STEP_COMPLETED,
                    finish_reason=ModelFinishReason.STOP,
                ),
            ],
        ]
    )
    runner = ReActRunner(
        model_adapter=adapter,
        tool_registry=ToolRegistry([EchoTool()]),
    )

    events = await _collect(runner, _turn_input())

    assert events[-1].content == "我先查一下。结果整体平稳。"


@pytest.mark.asyncio
async def test_runner_groups_tool_calls_before_their_results():
    adapter = FakeModelAdapter(
        [
            [
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TOOL_CALL,
                    tool_call_id="call-a",
                    tool_name="echo",
                    tool_arguments={"text": "甲"},
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TOOL_CALL,
                    tool_call_id="call-b",
                    tool_name="echo",
                    tool_arguments={"text": "乙"},
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.STEP_COMPLETED,
                    finish_reason=ModelFinishReason.TOOL_CALLS,
                ),
            ],
            [
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TEXT_DELTA,
                    delta="已完成。",
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.STEP_COMPLETED,
                    finish_reason=ModelFinishReason.STOP,
                ),
            ],
        ]
    )
    runner = ReActRunner(
        model_adapter=adapter,
        tool_registry=ToolRegistry([EchoTool()]),
    )

    await _collect(runner, _turn_input())

    tool_messages = adapter.requests[1].messages[-4:]
    assert [message.message_type for message in tool_messages] == [
        ChatMessageType.TOOL_CALL,
        ChatMessageType.TOOL_CALL,
        ChatMessageType.TOOL_RESULT,
        ChatMessageType.TOOL_RESULT,
    ]


@pytest.mark.asyncio
async def test_runner_updates_active_divination_for_later_tools():
    echo = EchoTool()
    adapter = FakeModelAdapter(
        [
            [
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TOOL_CALL,
                    tool_call_id="select",
                    tool_name="select_divination",
                    tool_arguments={"text": "选择"},
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TOOL_CALL,
                    tool_call_id="observe",
                    tool_name="echo",
                    tool_arguments={"text": "读取"},
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.STEP_COMPLETED,
                    finish_reason=ModelFinishReason.TOOL_CALLS,
                ),
            ],
            [
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TEXT_DELTA,
                    delta="完成。",
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.STEP_COMPLETED,
                    finish_reason=ModelFinishReason.STOP,
                ),
            ],
        ]
    )
    runner = ReActRunner(
        model_adapter=adapter,
        tool_registry=ToolRegistry(
            [SelectDivinationTool(), echo]
        ),
    )

    await _collect(runner, _turn_input())

    assert echo.contexts[0].active_divination_id == "b" * 32


@pytest.mark.asyncio
async def test_runner_turns_invalid_arguments_into_tool_observation():
    adapter = FakeModelAdapter(
        [
            [
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TOOL_CALL,
                    tool_call_id="call-invalid",
                    tool_name="echo",
                    tool_arguments={},
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.STEP_COMPLETED,
                    finish_reason=ModelFinishReason.TOOL_CALLS,
                ),
            ],
            [
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TEXT_DELTA,
                    delta="请补充工具参数。",
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.STEP_COMPLETED,
                    finish_reason=ModelFinishReason.STOP,
                ),
            ],
        ]
    )
    runner = ReActRunner(
        model_adapter=adapter,
        tool_registry=ToolRegistry([EchoTool()]),
    )

    events = await _collect(runner, _turn_input())

    failed = next(
        event
        for event in events
        if event.event_type == ChatEventType.TOOL_CALL_FAILED
    )
    assert failed.tool_result is not None
    assert failed.tool_result.error_code == "invalid_tool_arguments"
    assert failed.tool_result.retryable is True


@pytest.mark.asyncio
async def test_runner_stops_when_model_protocol_is_incomplete():
    adapter = FakeModelAdapter(
        [
            [
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TEXT_DELTA,
                    delta="没有结束事件",
                )
            ]
        ]
    )
    runner = ReActRunner(
        model_adapter=adapter,
        tool_registry=ToolRegistry(),
    )

    events = await _collect(runner, _turn_input())

    assert events[-1].event_type == ChatEventType.ERROR
    assert events[-1].error_code == "model_protocol_error"


@pytest.mark.asyncio
async def test_runner_converts_model_failure_and_length_limit_to_errors():
    failed_runner = ReActRunner(
        model_adapter=FakeModelAdapter([RuntimeError("model offline")]),
        tool_registry=ToolRegistry(),
    )
    failed_events = await _collect(failed_runner, _turn_input())
    assert failed_events[-1].error_code == "model_execution_error"

    truncated_runner = ReActRunner(
        model_adapter=FakeModelAdapter(
            [
                [
                    ModelStreamEvent(
                        event_type=ModelStreamEventType.STEP_COMPLETED,
                        finish_reason=ModelFinishReason.LENGTH,
                    )
                ]
            ]
        ),
        tool_registry=ToolRegistry(),
    )
    truncated_events = await _collect(truncated_runner, _turn_input())
    assert truncated_events[-1].error_code == "model_output_truncated"


@pytest.mark.asyncio
async def test_runner_enforces_maximum_react_steps():
    tool_steps = []
    for index in range(2):
        tool_steps.append(
            [
                ModelStreamEvent(
                    event_type=ModelStreamEventType.TOOL_CALL,
                    tool_call_id=f"call-{index}",
                    tool_name="missing_tool",
                    tool_arguments={},
                ),
                ModelStreamEvent(
                    event_type=ModelStreamEventType.STEP_COMPLETED,
                    finish_reason=ModelFinishReason.TOOL_CALLS,
                ),
            ]
        )
    runner = ReActRunner(
        model_adapter=FakeModelAdapter(tool_steps),
        tool_registry=ToolRegistry(),
        max_steps=2,
    )

    events = await _collect(runner, _turn_input())

    assert events[-1].event_type == ChatEventType.ERROR
    assert events[-1].error_code == "max_steps_exceeded"
    failed_calls = [
        event
        for event in events
        if event.event_type == ChatEventType.TOOL_CALL_FAILED
    ]
    assert len(failed_calls) == 2
    assert all(
        event.tool_result
        and event.tool_result.error_code == "unknown_tool"
        for event in failed_calls
    )
