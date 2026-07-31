"""多轮起卦固定工作流测试。"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.db.base import Base
from backend.db.session import enable_sqlite_foreign_keys
from backend.models.chat_session import ChatSession
from backend.models.user import User
from backend.repositories.chat_session import ChatSessionRepository
from backend.repositories.divination import DivinationRepository
from backend.schema.api.divination import QiguaMethod
from backend.services.chat_divination_workflow import ChatDivinationWorkflow
from backend.services.divination import DivinationService


@pytest.mark.asyncio
async def test_workflow_collects_missing_fields_then_creates_divination(
    tmp_path,
):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'workflow.db').as_posix()}",
        poolclass=NullPool,
    )
    enable_sqlite_foreign_keys(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as session:
        user = User()
        chat_session = ChatSession(user=user)
        session.add(user)
        await session.commit()
        user_id = user.id
        chat_session_id = chat_session.id

    async with factory() as session:
        sessions = ChatSessionRepository(session)
        divinations = DivinationRepository(session)
        service = DivinationService(divinations, session)
        workflow = ChatDivinationWorkflow(
            chat_session_repository=sessions,
            divination_service=service,
            session=session,
        )

        waiting = await workflow.process(
            user_id=user_id,
            session_id=chat_session_id,
            question="未来三个月的工作发展",
        )
        assert waiting.status == "needs_input"
        assert waiting.missing_fields == ["method"]

        persisted = await sessions.get_for_user(chat_session_id, user_id)
        assert persisted is not None
        assert persisted.workflow_state["payload"]["question"] == (
            "未来三个月的工作发展"
        )

        created = await workflow.process(
            user_id=user_id,
            session_id=chat_session_id,
            method=QiguaMethod.RANDOM,
        )
        assert created.status == "created"
        assert created.divination_id is not None
        assert created.paipan_markdown

        persisted = await sessions.get_for_user(chat_session_id, user_id)
        assert persisted is not None
        assert persisted.workflow_state is None
        assert persisted.active_divination_id == created.divination_id
        assert (
            await divinations.get_for_user(created.divination_id, user_id)
            is not None
        )

    await engine.dispose()


@pytest.mark.asyncio
async def test_coin_workflow_appends_tosses_and_resolves_now_on_creation(
    tmp_path,
):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'coin-workflow.db').as_posix()}",
        poolclass=NullPool,
    )
    enable_sqlite_foreign_keys(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as session:
        user = User()
        chat_session = ChatSession(user=user)
        session.add(user)
        await session.commit()
        user_id = user.id
        chat_session_id = chat_session.id

    async with factory() as session:
        sessions = ChatSessionRepository(session)
        divinations = DivinationRepository(session)
        workflow = ChatDivinationWorkflow(
            chat_session_repository=sessions,
            divination_service=DivinationService(divinations, session),
            session=session,
        )

        waiting = await workflow.process(
            user_id=user_id,
            session_id=chat_session_id,
            method=QiguaMethod.COIN,
            question="是否适合更换工作",
            coin_tosses=[["字", "字", "字"]],
        )

        assert waiting.status == "needs_input"
        assert waiting.missing_fields == ["time_mode", "coin_tosses"]
        assert waiting.draft is not None
        assert len(waiting.draft.coin_tosses) == 1

        created = await workflow.process(
            user_id=user_id,
            session_id=chat_session_id,
            time_mode="now",
            coin_tosses=[
                ["字", "字", "花"],
                ["字", "花", "花"],
                ["花", "花", "花"],
                ["字", "字", "花"],
                ["字", "花", "花"],
            ],
        )

        assert created.status == "created"
        assert created.qigua_time is not None
        divination = await divinations.get_for_user(
            created.divination_id,
            user_id,
        )
        assert divination is not None
        assert divination.numbers == [4, 2, 1, 3, 2, 1]

        persisted = await sessions.get_for_user(chat_session_id, user_id)
        assert persisted is not None
        assert persisted.workflow_state is None
        assert persisted.active_divination_id == created.divination_id

    await engine.dispose()


@pytest.mark.asyncio
async def test_workflow_requires_specific_time_and_can_cancel(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'cancel-workflow.db').as_posix()}",
        poolclass=NullPool,
    )
    enable_sqlite_foreign_keys(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as session:
        user = User()
        chat_session = ChatSession(user=user)
        session.add(user)
        await session.commit()
        user_id = user.id
        chat_session_id = chat_session.id

    async with factory() as session:
        sessions = ChatSessionRepository(session)
        workflow = ChatDivinationWorkflow(
            chat_session_repository=sessions,
            divination_service=DivinationService(
                DivinationRepository(session),
                session,
            ),
            session=session,
        )

        waiting = await workflow.process(
            user_id=user_id,
            session_id=chat_session_id,
            method=QiguaMethod.TIME,
            question="考试结果如何",
            time_mode="specified",
        )
        assert waiting.missing_fields == ["time"]
        assert await workflow.cancel(
            user_id=user_id,
            session_id=chat_session_id,
        )
        assert not await workflow.cancel(
            user_id=user_id,
            session_id=chat_session_id,
        )

        persisted = await sessions.get_for_user(chat_session_id, user_id)
        assert persisted is not None
        assert persisted.workflow_state is None

    await engine.dispose()
