"""聊天 ORM Model 的数据库约束测试。"""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import NullPool

from backend.db.base import Base
from backend.db.session import enable_sqlite_foreign_keys
from backend.models.chat_message import ChatMessage
from backend.models.chat_session import ChatSession
from backend.models.divination import Divination
from backend.models.user import User


def _create_test_engine(database_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
        poolclass=NullPool,
    )
    enable_sqlite_foreign_keys(engine)
    return engine


def test_chat_relationships_order_and_delete_policies(tmp_path):
    """验证消息排序、卦例 SET NULL 及会话 CASCADE 删除。"""

    async def scenario() -> None:
        engine = _create_test_engine(tmp_path / "chat-relations.db")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with factory() as session:
            user = User()
            session.add(user)
            await session.flush()

            divination = Divination(
                id="d" * 32,
                user_id=user.id,
                method="manual",
                question="聊天模型测试",
                qigua_time=user.created_at,
                numbers=[2, 1, 2, 2, 1, 2],
                paipan={"divination_id": "d" * 32},
            )
            chat_session = ChatSession(
                user_id=user.id,
                title="测试会话",
                active_divination=divination,
            )
            # 故意逆序添加，relationship 读取时应按 sequence 排序。
            chat_session.messages.extend(
                [
                    ChatMessage(
                        sequence=2,
                        role="assistant",
                        content="第二条",
                        divination=divination,
                    ),
                    ChatMessage(
                        sequence=1,
                        role="user",
                        content="第一条",
                    ),
                ]
            )
            session.add(chat_session)
            await session.commit()
            chat_session_id = chat_session.id
            message_ids = [message.id for message in chat_session.messages]

        async with factory() as session:
            loaded = await session.scalar(
                select(ChatSession)
                .where(ChatSession.id == chat_session_id)
                .options(selectinload(ChatSession.messages))
            )
            assert loaded is not None
            assert [message.sequence for message in loaded.messages] == [1, 2]
            assert loaded.active_divination_id == "d" * 32

            divination = await session.get(Divination, "d" * 32)
            assert divination is not None
            await session.delete(divination)
            await session.commit()

        async with factory() as session:
            loaded = await session.scalar(
                select(ChatSession)
                .where(ChatSession.id == chat_session_id)
                .options(selectinload(ChatSession.messages))
            )
            assert loaded is not None
            assert loaded.active_divination_id is None
            assert all(
                message.divination_id is None
                for message in loaded.messages
            )

            await session.delete(loaded)
            await session.commit()
            for message_id in message_ids:
                assert await session.get(ChatMessage, message_id) is None

        await engine.dispose()

    asyncio.run(scenario())


def test_message_sequence_is_unique_within_session(tmp_path):
    """同一会话不能出现重复消息序号。"""

    async def scenario() -> None:
        engine = _create_test_engine(tmp_path / "chat-sequence.db")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with factory() as session:
            user = User()
            chat_session = ChatSession(user=user)
            chat_session.messages.extend(
                [
                    ChatMessage(sequence=1, role="user", content="消息 A"),
                    ChatMessage(sequence=1, role="assistant", content="消息 B"),
                ]
            )
            session.add(chat_session)

            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
            else:
                raise AssertionError("重复 sequence 应触发数据库唯一约束")

        await engine.dispose()

    asyncio.run(scenario())


def test_deleting_user_cascades_chat_sessions_and_messages(tmp_path):
    """删除用户时，其会话和消息应一并删除。"""

    async def scenario() -> None:
        engine = _create_test_engine(tmp_path / "chat-user-cascade.db")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with factory() as session:
            user = User()
            chat_session = ChatSession(user=user)
            message = ChatMessage(
                session=chat_session,
                sequence=1,
                role="user",
                content="待级联删除",
            )
            session.add(user)
            await session.commit()
            user_id = user.id
            chat_session_id = chat_session.id
            message_id = message.id

        async with factory() as session:
            user = await session.get(User, user_id)
            assert user is not None
            await session.delete(user)
            await session.commit()

            assert await session.get(ChatSession, chat_session_id) is None
            assert await session.get(ChatMessage, message_id) is None

        await engine.dispose()

    asyncio.run(scenario())
