"""ChatContextBuilder 集成测试。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.agent.context_builder import (
    ChatContextBuilder,
    ChatSessionContextNotFoundError,
    InvalidChatHistoryError,
)
from backend.db.base import Base
from backend.db.session import enable_sqlite_foreign_keys
from backend.models.chat_message import ChatMessage
from backend.models.chat_session import ChatSession
from backend.models.divination import Divination
from backend.models.user import User
from backend.repositories.chat_message import ChatMessageRepository
from backend.repositories.chat_session import ChatSessionRepository


def _create_test_engine(database_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
        poolclass=NullPool,
    )
    enable_sqlite_foreign_keys(engine)
    return engine


@pytest.mark.asyncio
async def test_context_builder_loads_owned_summary_and_completed_messages(
    tmp_path,
):
    engine = _create_test_engine(tmp_path / "context-builder.db")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as session:
        owner = User()
        other_user = User()
        session.add_all([owner, other_user])
        await session.flush()

        divination = Divination(
            id="d" * 32,
            user_id=owner.id,
            method="manual",
            question="测试",
            qigua_time=datetime.now(timezone.utc),
            paipan={"divination_id": "d" * 32},
        )
        chat_session = ChatSession(
            user_id=owner.id,
            title="上下文测试",
            summary="用户此前询问工作发展。",
            summary_through_sequence=2,
            next_message_sequence=7,
            active_divination=divination,
            model="session-model",
        )
        chat_session.messages.extend(
            [
                ChatMessage(
                    sequence=1,
                    role="user",
                    content="已被摘要覆盖的消息",
                ),
                ChatMessage(
                    sequence=2,
                    role="assistant",
                    content="已被摘要覆盖的回答",
                ),
                ChatMessage(
                    sequence=3,
                    role="user",
                    content="最近追问",
                ),
                ChatMessage(
                    sequence=4,
                    role="assistant",
                    content=None,
                    status="pending",
                ),
                ChatMessage(
                    sequence=5,
                    role="assistant",
                    content=None,
                    status="cancelled",
                ),
                ChatMessage(
                    sequence=6,
                    role="assistant",
                    content="最近回答",
                ),
            ]
        )
        session.add(chat_session)
        await session.commit()
        owner_id = owner.id
        other_user_id = other_user.id
        session_id = chat_session.id

    async with factory() as session:
        builder = ChatContextBuilder(
            session_repository=ChatSessionRepository(session),
            message_repository=ChatMessageRepository(session),
            recent_message_limit=10,
        )
        context = await builder.build(
            user_id=owner_id,
            session_id=session_id,
            user_message="  请继续解释世爻  ",
        )

        assert context.user_message == "请继续解释世爻"
        assert context.session_summary == "用户此前询问工作发展。"
        assert context.summary_through_sequence == 2
        assert [message.sequence for message in context.recent_messages] == [
            3,
            6,
        ]
        assert context.active_divination_id == "d" * 32
        assert context.model == "session-model"

        overridden = await builder.build(
            user_id=owner_id,
            session_id=session_id,
            user_message="切换模型",
            model="request-model",
        )
        assert overridden.model == "request-model"

        with pytest.raises(ValidationError):
            await builder.build(
                user_id=owner_id,
                session_id=session_id,
                user_message="空白模型名",
                model=" ",
            )

        with pytest.raises(ChatSessionContextNotFoundError):
            await builder.build(
                user_id=other_user_id,
                session_id=session_id,
                user_message="越权读取",
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_context_builder_reports_invalid_completed_history(tmp_path):
    engine = _create_test_engine(tmp_path / "invalid-history.db")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as session:
        user = User()
        chat_session = ChatSession(user=user)
        chat_session.messages.append(
            ChatMessage(
                sequence=1,
                role="assistant",
                content=None,
                status="completed",
            )
        )
        session.add(user)
        await session.commit()
        user_id = user.id
        session_id = chat_session.id

    async with factory() as session:
        builder = ChatContextBuilder(
            session_repository=ChatSessionRepository(session),
            message_repository=ChatMessageRepository(session),
        )
        with pytest.raises(InvalidChatHistoryError):
            await builder.build(
                user_id=user_id,
                session_id=session_id,
                user_message="测试",
            )

    await engine.dispose()


def test_context_builder_rejects_invalid_recent_message_limit():
    with pytest.raises(ValueError, match="大于等于 1"):
        ChatContextBuilder(
            session_repository=None,  # type: ignore[arg-type]
            message_repository=None,  # type: ignore[arg-type]
            recent_message_limit=0,
        )
