"""ChatService 流式持久化集成测试。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.agent.context_builder import ChatContextBuilder
from backend.db.base import Base
from backend.db.session import enable_sqlite_foreign_keys
from backend.models.divination import Divination
from backend.models.user import User
from backend.repositories.chat_message import ChatMessageRepository
from backend.repositories.chat_session import ChatSessionRepository
from backend.repositories.divination import DivinationRepository
from backend.schema.agent import (
    ChatEvent,
    ChatEventType,
    ToolResult,
)
from backend.schema.api.chat import ChatSessionCreate
from backend.services.chat import ChatService


class FakeRunner:
    def __init__(self, divination_id: str):
        self.divination_id = divination_id
        self.inputs = []

    async def run(self, turn_input):
        self.inputs.append(turn_input)
        yield ChatEvent(
            event_type=ChatEventType.TOOL_CALL_STARTED,
            tool_call_id="call-1",
            tool_name="get_divination",
            tool_arguments={"divination_id": self.divination_id},
        )
        yield ChatEvent(
            event_type=ChatEventType.TOOL_CALL_COMPLETED,
            tool_call_id="call-1",
            tool_name="get_divination",
            tool_result=ToolResult(
                success=True,
                model_content="真实排盘",
                data={"divination_id": self.divination_id},
            ),
        )
        yield ChatEvent(
            event_type=ChatEventType.TEXT_DELTA,
            content="整体",
        )
        yield ChatEvent(
            event_type=ChatEventType.TEXT_DELTA,
            content="平稳。",
        )
        yield ChatEvent(
            event_type=ChatEventType.MESSAGE_COMPLETED,
            content="整体平稳。",
        )


class FakeSummarizer:
    def __init__(self):
        self.calls = []

    async def maybe_summarize(self, **kwargs):
        self.calls.append(kwargs)
        return False


@pytest.mark.asyncio
async def test_chat_service_persists_observable_react_messages(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'chat-service.db').as_posix()}",
        poolclass=NullPool,
    )
    enable_sqlite_foreign_keys(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as session:
        user = User()
        divination = Divination(
            id="d" * 32,
            user=user,
            method="random",
            question="工作如何",
            qigua_time=datetime.now(timezone.utc),
            paipan={
                "ben_gua": {"name": "乾为天"},
            },
        )
        session.add(user)
        await session.commit()
        user_id = user.id
        divination_id = divination.id

    async with factory() as session:
        session_repository = ChatSessionRepository(session)
        message_repository = ChatMessageRepository(session)
        divination_repository = DivinationRepository(session)
        runner = FakeRunner(divination_id)
        summarizer = FakeSummarizer()
        service = ChatService(
            session_repository=session_repository,
            message_repository=message_repository,
            divination_repository=divination_repository,
            context_builder=ChatContextBuilder(
                session_repository=session_repository,
                message_repository=message_repository,
            ),
            runner=runner,  # type: ignore[arg-type]
            summarizer=summarizer,  # type: ignore[arg-type]
            session=session,
        )
        created = await service.create_session(
            ChatSessionCreate(),
            user_id,
        )

        events = [
            event
            async for event in service.stream_reply(
                session_id=created.id,
                user_id=user_id,
                user_message="请继续分析",
            )
        ]
        messages = await service.list_messages(
            created.id,
            user_id,
        )
        updated = await service.get_session(created.id, user_id)

        assert events[-1].event_type == ChatEventType.MESSAGE_COMPLETED
        assert runner.inputs[0].recent_messages == []
        assert [message.sequence for message in messages] == [1, 2, 3, 4]
        assert [
            (message.role, message.message_type)
            for message in messages
        ] == [
            ("user", "text"),
            ("assistant", "tool_call"),
            ("tool", "tool_result"),
            ("assistant", "text"),
        ]
        assert messages[-1].content == "整体平稳。"
        assert updated.active_divination_id == divination_id
        assert updated.title == "请继续分析"
        assert len(summarizer.calls) == 1

    await engine.dispose()
