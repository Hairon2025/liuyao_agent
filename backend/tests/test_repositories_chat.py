"""聊天 Repository 集成测试。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.db.base import Base
from backend.db.session import enable_sqlite_foreign_keys
from backend.models.chat_message import ChatMessage
from backend.models.chat_session import ChatSession
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


def test_chat_repositories_enforce_ownership_and_support_context_queries(
    tmp_path,
):
    """覆盖会话所有权、消息游标分页、工具配对和更新。"""

    async def scenario() -> None:
        engine = _create_test_engine(tmp_path / "chat-repositories.db")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        now = datetime.now(timezone.utc)
        async with factory() as session:
            user_a = User(display_name="用户甲")
            user_b = User(display_name="用户乙")
            session.add_all([user_a, user_b])
            await session.flush()

            sessions = ChatSessionRepository(session)
            active = await sessions.add(
                ChatSession(
                    user_id=user_a.id,
                    title="进行中的会话",
                    last_message_at=now - timedelta(minutes=5),
                )
            )
            archived = await sessions.add(
                ChatSession(
                    user_id=user_a.id,
                    title="已归档会话",
                    status="archived",
                    last_message_at=now,
                )
            )
            other = await sessions.add(
                ChatSession(
                    user_id=user_b.id,
                    title="其他用户会话",
                    last_message_at=now + timedelta(minutes=5),
                )
            )
            await session.commit()
            user_a_id = user_a.id
            user_b_id = user_b.id
            active_id = active.id
            archived_id = archived.id
            other_id = other.id

        async with factory() as session:
            sessions = ChatSessionRepository(session)

            assert (
                await sessions.get_for_user(active_id, user_a_id)
            ) is not None
            assert await sessions.get_for_user(active_id, user_b_id) is None
            assert await sessions.get_for_user(other_id, user_a_id) is None

            user_a_sessions = await sessions.list_for_user(user_a_id)
            assert [item.id for item in user_a_sessions] == [
                archived_id,
                active_id,
            ]
            active_sessions = await sessions.list_for_user(
                user_a_id,
                status="active",
            )
            assert [item.id for item in active_sessions] == [active_id]

            # 非所有者无法预留序号。
            assert (
                await sessions.reserve_next_message_sequence(
                    active_id,
                    user_b_id,
                )
                is None
            )

            messages = ChatMessageRepository(session)
            assert (
                await messages.add_for_user(
                    ChatMessage(
                        session_id=active_id,
                        sequence=99,
                        role="user",
                        content="越权消息",
                    ),
                    user_b_id,
                )
                is None
            )
            sequence_1 = await sessions.reserve_next_message_sequence(
                active_id,
                user_a_id,
            )
            sequence_2 = await sessions.reserve_next_message_sequence(
                active_id,
                user_a_id,
            )
            sequence_3 = await sessions.reserve_next_message_sequence(
                active_id,
                user_a_id,
            )
            assert (sequence_1, sequence_2, sequence_3) == (1, 2, 3)

            user_message = await messages.add_for_user(
                ChatMessage(
                    session_id=active_id,
                    sequence=sequence_1,
                    role="user",
                    content="帮我起一卦",
                ),
                user_a_id,
            )
            tool_call = await messages.add_for_user(
                ChatMessage(
                    session_id=active_id,
                    sequence=sequence_2,
                    role="assistant",
                    message_type="tool_call",
                    tool_name="random_divination",
                    tool_call_id="call-001",
                    payload={"question": "近期工作如何"},
                ),
                user_a_id,
            )
            tool_result = await messages.add_for_user(
                ChatMessage(
                    session_id=active_id,
                    sequence=sequence_3,
                    role="tool",
                    message_type="tool_result",
                    tool_name="random_divination",
                    tool_call_id="call-001",
                    payload={"divination_id": "example"},
                ),
                user_a_id,
            )
            assert user_message is not None
            assert tool_call is not None
            assert tool_result is not None
            await session.commit()
            message_id = user_message.id
            tool_call_id = tool_call.id
            tool_result_id = tool_result.id

        async with factory() as session:
            sessions = ChatSessionRepository(session)
            messages = ChatMessageRepository(session)

            assert (
                await messages.get_for_user(message_id, user_a_id)
            ) is not None
            assert await messages.get_for_user(message_id, user_b_id) is None
            assert (
                await messages.list_for_session(
                    active_id,
                    user_b_id,
                )
                == []
            )

            first_page = await messages.list_for_session(
                active_id,
                user_a_id,
                limit=2,
            )
            second_page = await messages.list_for_session(
                active_id,
                user_a_id,
                after_sequence=2,
            )
            assert [item.sequence for item in first_page] == [1, 2]
            assert [item.sequence for item in second_page] == [3]

            recent = await messages.list_recent_for_session(
                active_id,
                user_a_id,
                limit=2,
            )
            assert [item.sequence for item in recent] == [2, 3]

            tool_pair = await messages.list_by_tool_call_id_for_user(
                active_id,
                user_a_id,
                "call-001",
            )
            assert [item.id for item in tool_pair] == [
                tool_call_id,
                tool_result_id,
            ]

            loaded_message = await messages.get_for_user(
                message_id,
                user_a_id,
            )
            assert loaded_message is not None
            await messages.update(
                loaded_message,
                {
                    "content": "帮我随机起一卦",
                    "token_count": 9,
                },
            )
            loaded_session = await sessions.get_for_user(
                active_id,
                user_a_id,
            )
            assert loaded_session is not None
            await sessions.update(
                loaded_session,
                {"title": "工作问卦"},
            )
            await session.commit()

        async with factory() as session:
            sessions = ChatSessionRepository(session)
            messages = ChatMessageRepository(session)
            updated_session = await sessions.get_for_user(
                active_id,
                user_a_id,
            )
            updated_message = await messages.get_for_user(
                message_id,
                user_a_id,
            )
            assert updated_session is not None
            assert updated_session.title == "工作问卦"
            assert updated_session.next_message_sequence == 4
            assert updated_message is not None
            assert updated_message.content == "帮我随机起一卦"
            assert updated_message.token_count == 9

        await engine.dispose()

    asyncio.run(scenario())


def test_sequence_reservation_is_rolled_back_with_transaction(tmp_path):
    """消息写入失败并回滚时，预留序号也应被归还。"""

    async def scenario() -> None:
        engine = _create_test_engine(tmp_path / "chat-sequence-rollback.db")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with factory() as session:
            user = User()
            chat_session = ChatSession(user=user)
            session.add(user)
            await session.commit()
            user_id = user.id
            session_id = chat_session.id

        async with factory() as session:
            repository = ChatSessionRepository(session)
            assert (
                await repository.reserve_next_message_sequence(
                    session_id,
                    user_id,
                )
                == 1
            )
            await session.rollback()

        async with factory() as session:
            repository = ChatSessionRepository(session)
            assert (
                await repository.reserve_next_message_sequence(
                    session_id,
                    user_id,
                )
                == 1
            )
            await session.commit()

        await engine.dispose()

    asyncio.run(scenario())
