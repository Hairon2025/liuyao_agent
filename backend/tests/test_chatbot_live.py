"""可选的真实模型冒烟测试。

默认跳过；配置后可验证当前 OpenAI-compatible 服务是否真的支持 Agent 工具声明：

    RUN_LLM_INTEGRATION_TESTS=1 python -m pytest -q \
        backend/tests/test_chatbot_live.py
"""
from __future__ import annotations

import os
import uuid

import pytest
from agents.memory import SQLiteSession

from backend.agent.chatbot_agent import LiuYaoChatbot
from backend.agent.runtime.context import AgentRunContext
from backend.config.settings import settings
from backend.schema.agent import ChatEventType


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LLM_INTEGRATION_TESTS") != "1",
    reason="未启用真实 LLM 集成测试",
)
async def test_chatbot_can_complete_plain_chat_with_configured_provider(
    tmp_path,
):
    if not settings.llm_api_key:
        pytest.skip("未配置 LLM_API_KEY")

    chatbot = LiuYaoChatbot(max_turns=3)
    context = AgentRunContext(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        divination_service=object(),  # type: ignore[arg-type]
        chat_divination_workflow=object(),  # type: ignore[arg-type]
    )
    session = SQLiteSession(
        "chatbot-live-smoke",
        db_path=tmp_path / "agent-live.db",
    )

    events = [
        event
        async for event in chatbot.stream(
            user_message="你好，请简单介绍你能做什么。",
            context=context,
            session=session,
        )
    ]

    assert not any(
        event.event_type == ChatEventType.ERROR for event in events
    )
    assert any(
        event.event_type == ChatEventType.MESSAGE_COMPLETED
        for event in events
    )
