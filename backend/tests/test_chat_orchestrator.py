"""聊天多 Agent 串行编排测试。"""
from __future__ import annotations

import uuid

import pytest

from backend.agent.chat_orchestrator import ChatAgentOrchestrator
from backend.agent.runtime.context import AgentRunContext
from backend.schema.agent import ChatEvent, ChatEventType, ToolResult


class FakeCoordinator:
    async def stream(self, **kwargs):
        yield ChatEvent(
            event_type=ChatEventType.TOOL_CALL_STARTED,
            tool_call_id="create-1",
            tool_name="process_divination_request",
            tool_arguments={"method": "random", "question": "工作"},
        )
        yield ChatEvent(
            event_type=ChatEventType.TOOL_CALL_COMPLETED,
            tool_call_id="create-1",
            tool_name="process_divination_request",
            tool_result=ToolResult(
                success=True,
                model_content="已完成排盘",
                data={
                    "status": "created",
                    "divination_id": "d" * 32,
                },
            ),
        )
        # 这段协调 Agent 文本不应展示，也不应成为业务消息。
        yield ChatEvent(
            event_type=ChatEventType.TEXT_DELTA,
            content="协调 Agent 的重复说明",
        )
        yield ChatEvent(
            event_type=ChatEventType.MESSAGE_COMPLETED,
            content="协调 Agent 的重复说明",
        )


class FakeAnalyst:
    async def interpret_stream(self, markdown):
        assert markdown == "# 真实排盘"
        yield "正式"
        yield "解读"


class FakeDivinationService:
    def __init__(self):
        self.saved = []

    async def get_markdown(self, divination_id, user_id):
        assert divination_id == "d" * 32
        return "# 真实排盘"

    async def save_interpretation(self, divination_id, user_id, detail):
        self.saved.append((divination_id, user_id, detail))


class FakeSession:
    def __init__(self):
        self.items = []

    async def add_items(self, items):
        self.items.extend(items)


@pytest.mark.asyncio
async def test_new_divination_uses_analyst_and_saves_canonical_report():
    user_id = uuid.uuid4()
    service = FakeDivinationService()
    sdk_session = FakeSession()
    orchestrator = ChatAgentOrchestrator(
        coordinator=FakeCoordinator(),  # type: ignore[arg-type]
        analyst=FakeAnalyst(),  # type: ignore[arg-type]
        divination_service=service,  # type: ignore[arg-type]
    )
    context = AgentRunContext(
        user_id=user_id,
        session_id=uuid.uuid4(),
        divination_service=service,  # type: ignore[arg-type]
        chat_divination_workflow=object(),  # type: ignore[arg-type]
    )

    events = [
        event
        async for event in orchestrator.stream(
            user_message="随机起卦看工作",
            context=context,
            session=sdk_session,  # type: ignore[arg-type]
        )
    ]

    assert [event.event_type for event in events] == [
        ChatEventType.TOOL_CALL_STARTED,
        ChatEventType.TOOL_CALL_COMPLETED,
        ChatEventType.TEXT_DELTA,
        ChatEventType.TEXT_DELTA,
        ChatEventType.MESSAGE_COMPLETED,
    ]
    assert events[-1].content == "正式解读"
    assert service.saved == [(("d" * 32), user_id, "正式解读")]
    assert sdk_session.items == [
        {"role": "assistant", "content": "正式解读"}
    ]

