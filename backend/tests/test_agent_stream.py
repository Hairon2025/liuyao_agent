"""Agents SDK 流事件到前端 ChatEvent 的适配测试。"""
from __future__ import annotations

import json
import uuid

import pytest
from agents import Agent, RawResponsesStreamEvent, RunItemStreamEvent
from agents.items import ToolCallItem, ToolCallOutputItem
from openai.types.responses import ResponseTextDeltaEvent

from backend.agent.runtime.context import AgentRunContext
from backend.agent.runtime.stream import AgentStreamAdapter
from backend.schema.agent import ChatEventType, ToolResult


class FakeStreamingResult:
    final_output = "完整回答"

    def __init__(self, events):
        self._events = events

    async def stream_events(self):
        for event in self._events:
            yield event


@pytest.mark.asyncio
async def test_stream_adapter_exposes_only_business_tool_events():
    agent = Agent(name="test", instructions="test", model="gpt-test")
    result_json = ToolResult(
        success=True,
        model_content="已创建卦例",
        data={"divination_id": "a" * 32},
    ).model_dump_json()
    events = [
        RawResponsesStreamEvent(
            data=ResponseTextDeltaEvent(
                content_index=0,
                delta="正在处理",
                item_id="message-1",
                logprobs=[],
                output_index=0,
                sequence_number=1,
                type="response.output_text.delta",
            )
        ),
        # 未注册为产品业务工具的内部事件不应暴露到界面。
        RunItemStreamEvent(
            name="tool_called",
            item=ToolCallItem(
                agent=agent,
                raw_item={
                    "type": "function_call",
                    "name": "load_skill",
                    "call_id": "skill-call",
                    "arguments": '{"skill_name":"divination-intake"}',
                },
            ),
        ),
        RunItemStreamEvent(
            name="tool_called",
            item=ToolCallItem(
                agent=agent,
                raw_item={
                    "type": "function_call",
                    "name": "process_divination_request",
                    "call_id": "business-call",
                    "arguments": json.dumps(
                        {"method": "random", "question": "工作"}
                    ),
                },
            ),
        ),
        RunItemStreamEvent(
            name="tool_output",
            item=ToolCallOutputItem(
                agent=agent,
                raw_item={
                    "type": "function_call_output",
                    "call_id": "business-call",
                    "output": result_json,
                },
                output=result_json,
            ),
        ),
    ]
    context = AgentRunContext(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        divination_service=object(),  # type: ignore[arg-type]
        chat_divination_workflow=object(),  # type: ignore[arg-type]
    )

    adapted = [
        event
        async for event in AgentStreamAdapter().stream(
            FakeStreamingResult(events),  # type: ignore[arg-type]
            context,
        )
    ]

    assert [event.event_type for event in adapted] == [
        ChatEventType.TEXT_DELTA,
        ChatEventType.TOOL_CALL_STARTED,
        ChatEventType.TOOL_CALL_COMPLETED,
        ChatEventType.MESSAGE_COMPLETED,
    ]
    assert adapted[1].tool_arguments == {
        "method": "random",
        "question": "工作",
    }
    assert context.active_divination_id == "a" * 32
