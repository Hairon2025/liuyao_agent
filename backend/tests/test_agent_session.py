"""Agents SDK SQLAlchemySession 的数据库集成测试。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.agent.runtime.session import AgentSessionFactory
from backend.db.base import Base
from backend.models.agent_session import AgentMessageRecord, AgentSessionRecord


@pytest.mark.asyncio
async def test_sdk_session_persists_limits_and_clears_history(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'sdk-session.db').as_posix()}",
        poolclass=NullPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_id = uuid.uuid4()
    sdk_factory = AgentSessionFactory(engine=engine, recent_limit=2)
    sdk_session = sdk_factory.create(session_id)
    await sdk_session.add_items(
        [
            {"role": "user", "content": "第一条"},
            {"role": "assistant", "content": "第二条"},
            {"role": "user", "content": "第三条"},
        ]
    )

    assert [item["content"] for item in await sdk_session.get_items()] == [
        "第二条",
        "第三条",
    ]

    await sdk_factory.clear(session_id)
    async_session_factory = async_sessionmaker(engine)
    async with async_session_factory() as session:
        assert await session.get(AgentSessionRecord, str(session_id)) is None
        rows = await session.scalars(
            select(AgentMessageRecord).where(
                AgentMessageRecord.session_id == str(session_id)
            )
        )
        assert list(rows) == []

    await engine.dispose()
