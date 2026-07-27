"""ChatContextSummarizer 测试。"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.agent.context_summarizer import ChatContextSummarizer
from backend.agent.model import ChatModelAdapter
from backend.db.base import Base
from backend.db.session import enable_sqlite_foreign_keys
from backend.models.chat_message import ChatMessage
from backend.models.chat_session import ChatSession
from backend.models.user import User
from backend.repositories.chat_message import ChatMessageRepository
from backend.repositories.chat_session import ChatSessionRepository
from backend.schema.agent import (
    ModelFinishReason,
    ModelRequest,
    ModelStreamEvent,
    ModelStreamEventType,
)


class SummaryAdapter(ChatModelAdapter):
    def __init__(self):
        self.requests: list[ModelRequest] = []

    def stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)

        async def generate():
            yield ModelStreamEvent(
                event_type=ModelStreamEventType.TEXT_DELTA,
                delta="- 用户正在询问工作。",
            )
            yield ModelStreamEvent(
                event_type=ModelStreamEventType.STEP_COMPLETED,
                finish_reason=ModelFinishReason.STOP,
            )

        return generate()


@pytest.mark.asyncio
async def test_summarizer_updates_summary_cursor_and_keeps_recent(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'summary.db').as_posix()}",
        poolclass=NullPool,
    )
    enable_sqlite_foreign_keys(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as session:
        user = User()
        chat_session = ChatSession(
            user=user,
            next_message_sequence=6,
        )
        for sequence in range(1, 6):
            chat_session.messages.append(
                ChatMessage(
                    sequence=sequence,
                    role="user" if sequence % 2 else "assistant",
                    content=f"消息 {sequence}",
                )
            )
        session.add(user)
        await session.commit()
        user_id = user.id
        session_id = chat_session.id

    adapter = SummaryAdapter()
    async with factory() as session:
        session_repository = ChatSessionRepository(session)
        summarizer = ChatContextSummarizer(
            session_repository=session_repository,
            message_repository=ChatMessageRepository(session),
            model_adapter=adapter,
            trigger_messages=5,
            keep_recent=1,
        )

        changed = await summarizer.maybe_summarize(
            user_id=user_id,
            session_id=session_id,
        )
        row = await session_repository.get_for_user(
            session_id,
            user_id,
        )

        assert changed is True
        assert row is not None
        assert row.summary == "- 用户正在询问工作。"
        assert row.summary_through_sequence == 4
        assert "消息 4" in adapter.requests[0].messages[0].content
        assert "消息 5" not in adapter.requests[0].messages[0].content

    await engine.dispose()
