"""OpenAI Chat Completions 适配器测试。"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.agent.model.openai_chat import OpenAIChatModelAdapter
from backend.schema.agent import (
    ChatMessageType,
    ChatRole,
    ModelFinishReason,
    ModelMessage,
    ModelRequest,
    ModelStreamEventType,
)


class FakeCompletions:
    def __init__(self, chunks):
        self._chunks = chunks
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs

        async def generate():
            for chunk in self._chunks:
                yield chunk

        return generate()


class FakeClient:
    def __init__(self, chunks):
        self.chat = SimpleNamespace(
            completions=FakeCompletions(chunks)
        )


def _chunk(
    *,
    content=None,
    tool_calls=None,
    finish_reason=None,
):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=content,
                    tool_calls=tool_calls,
                ),
                finish_reason=finish_reason,
            )
        ]
    )


def _tool_delta(index, *, call_id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        ),
    )


@pytest.mark.asyncio
async def test_adapter_aggregates_streamed_tool_arguments():
    client = FakeClient(
        [
            _chunk(content="我先查询。"),
            _chunk(
                tool_calls=[
                    _tool_delta(
                        0,
                        call_id="call-1",
                        name="get_divination",
                        arguments='{"divination_',
                    )
                ]
            ),
            _chunk(
                tool_calls=[
                    _tool_delta(
                        0,
                        arguments='id":"abc"}',
                    )
                ],
                finish_reason="tool_calls",
            ),
        ]
    )
    adapter = OpenAIChatModelAdapter(
        client=client,
        default_model="test-model",
    )
    request = ModelRequest(
        instructions="系统提示",
        messages=[ModelMessage(role=ChatRole.USER, content="查询")],
    )

    events = [event async for event in adapter.stream(request)]

    assert [event.event_type for event in events] == [
        ModelStreamEventType.TEXT_DELTA,
        ModelStreamEventType.TOOL_CALL,
        ModelStreamEventType.STEP_COMPLETED,
    ]
    assert events[1].tool_call_id == "call-1"
    assert events[1].tool_arguments == {"divination_id": "abc"}
    assert events[-1].finish_reason == ModelFinishReason.TOOL_CALLS
    assert client.chat.completions.kwargs["model"] == "test-model"


@pytest.mark.asyncio
async def test_adapter_groups_consecutive_internal_tool_calls():
    client = FakeClient([_chunk(content="完成", finish_reason="stop")])
    adapter = OpenAIChatModelAdapter(client=client)
    request = ModelRequest(
        messages=[
            ModelMessage(role=ChatRole.USER, content="开始"),
            ModelMessage(
                role=ChatRole.ASSISTANT,
                message_type=ChatMessageType.TOOL_CALL,
                tool_call_id="a",
                tool_name="first",
                payload={"value": 1},
            ),
            ModelMessage(
                role=ChatRole.ASSISTANT,
                message_type=ChatMessageType.TOOL_CALL,
                tool_call_id="b",
                tool_name="second",
                payload={"value": 2},
            ),
            ModelMessage(
                role=ChatRole.TOOL,
                message_type=ChatMessageType.TOOL_RESULT,
                tool_call_id="a",
                tool_name="first",
                content="一",
            ),
            ModelMessage(
                role=ChatRole.TOOL,
                message_type=ChatMessageType.TOOL_RESULT,
                tool_call_id="b",
                tool_name="second",
                content="二",
            ),
        ],
    )

    events = [event async for event in adapter.stream(request)]

    sent = client.chat.completions.kwargs["messages"]
    assert len(sent[1]["tool_calls"]) == 2
    assert json.loads(
        sent[1]["tool_calls"][1]["function"]["arguments"]
    ) == {"value": 2}
    assert sent[2]["tool_call_id"] == "a"
    assert events[-1].finish_reason == ModelFinishReason.STOP
