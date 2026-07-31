"""Chatbot 长期记忆压缩与 Session 注入测试。"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.agent.memory.compactor import ChatMemoryCompactor
from backend.agent.runtime.session import AgentSessionFactory
from backend.db.base import Base
from backend.models.agent_session import AgentMessageRecord
from backend.models.chat_session import ChatSession
from backend.models.user import User
from backend.repositories.agent_memory import AgentMemoryRepository
from backend.repositories.chat_session import ChatSessionRepository
from backend.schema.agent.memory import ConversationMemory


class FakeMemorySummaryAgent:
    def __init__(self):
        self.calls: list[dict] = []

    async def summarize(self, **kwargs) -> ConversationMemory:
        self.calls.append(kwargs)
        return ConversationMemory(
            current_focus="继续分析工作卦",
            user_context=["用户关注未来三个月"],
            key_conclusions=["后期存在变化"],
            unresolved_questions=["具体应期尚未确认"],
        )


def test_compactor_moves_cutoff_to_complete_user_turn():
    compactor = ChatMemoryCompactor(
        session_repository=None,  # type: ignore[arg-type]
        memory_repository=None,  # type: ignore[arg-type]
        summary_agent=None,  # type: ignore[arg-type]
        session=None,  # type: ignore[arg-type]
        trigger_items=8,
        keep_recent_items=3,
        input_max_chars=4000,
        context_recent_limit=10,
    )
    raw_items = [
        {"role": "user", "content": "第一轮"},
        {"type": "function_call", "name": "create_divination"},
        {"type": "function_call_output", "output": "第一轮工具结果"},
        {"role": "assistant", "content": "第一轮回答"},
        {"role": "user", "content": "第二轮"},
        {"type": "function_call", "name": "read_divination"},
        {"type": "function_call_output", "output": "第二轮工具结果"},
        {"role": "assistant", "content": "第二轮回答"},
    ]
    records = [
        AgentMessageRecord(
            id=index + 1,
            session_id="safe-boundary",
            message_data=json.dumps(item, ensure_ascii=False),
        )
        for index, item in enumerate(raw_items)
    ]

    # 固定保留 3 条会切在第二轮的 function_call 上；实际应回退到 user。
    assert compactor._find_safe_retain_start(records) == 4


def test_compactor_only_selects_complete_turns_within_input_budget():
    compactor = ChatMemoryCompactor(
        session_repository=None,  # type: ignore[arg-type]
        memory_repository=None,  # type: ignore[arg-type]
        summary_agent=None,  # type: ignore[arg-type]
        session=None,  # type: ignore[arg-type]
        trigger_items=4,
        keep_recent_items=2,
        input_max_chars=1000,
        context_recent_limit=10,
    )
    records = [
        AgentMessageRecord(
            id=index + 1,
            session_id="input-budget",
            message_data=json.dumps(
                {"role": "user", "content": character * 600}
            ),
        )
        for index, character in enumerate(("甲", "乙"))
    ]

    selected, normalized = compactor._select_candidates_within_budget(
        records
    )

    assert [record.id for record in selected] == [1]
    assert len(normalized) == 1
    assert "甲" in normalized[0]
    assert "乙" not in normalized[0]


@pytest.mark.asyncio
async def test_compactor_summarizes_old_items_and_memory_session_injects_it(
    tmp_path,
):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'chat-memory.db').as_posix()}",
        poolclass=NullPool,
    )
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

    raw_factory = AgentSessionFactory(engine=engine, recent_limit=10)
    sdk_session = raw_factory.create(session_id)
    await sdk_session.add_items(
        [
            {"role": "user", "content": "第一轮问题"},
            {"role": "assistant", "content": "第一轮回答"},
            {"role": "user", "content": "第二轮问题"},
            {"role": "assistant", "content": "第二轮回答"},
            {"role": "user", "content": "最近问题"},
            {"role": "assistant", "content": "最近回答"},
        ]
    )

    async with factory() as session:
        summary_agent = FakeMemorySummaryAgent()
        compactor = ChatMemoryCompactor(
            session_repository=ChatSessionRepository(session),
            memory_repository=AgentMemoryRepository(session),
            summary_agent=summary_agent,  # type: ignore[arg-type]
            session=session,
            trigger_items=6,
            keep_recent_items=2,
            input_max_chars=4000,
            context_recent_limit=10,
        )
        result = await compactor.compact_if_needed(
            session_id=session_id,
            user_id=user_id,
        )
        loaded = await session.get(ChatSession, session_id)
        remaining = list(
            await session.scalars(
                select(AgentMessageRecord)
                .where(
                    AgentMessageRecord.session_id == str(session_id)
                )
                .order_by(AgentMessageRecord.id.asc())
            )
        )

        assert result.compacted is True
        assert result.compacted_items == 4
        assert result.retained_items == 2
        assert len(summary_agent.calls) == 1
        assert summary_agent.calls[0]["previous_memory"] is None
        assert len(summary_agent.calls[0]["conversation_items"]) == 4
        assert loaded is not None
        assert loaded.summary == result.summary
        assert loaded.summary_through_agent_message_id > 0
        assert loaded.summary_updated_at is not None
        assert len(remaining) == 2

        second = await compactor.compact_if_needed(
            session_id=session_id,
            user_id=user_id,
        )
        assert second.compacted is False
        assert len(summary_agent.calls) == 1

    memory_factory = AgentSessionFactory(
        engine=engine,
        recent_limit=10,
        memory_enabled=True,
    )
    memory_session = memory_factory.create(
        session_id,
        memory_summary=result.summary,
    )
    items = await memory_session.get_items()

    assert len(items) == 3
    assert items[0]["role"] == "system"
    assert "继续分析工作卦" in str(items[0]["content"])
    assert [item["content"] for item in items[1:]] == [
        "最近问题",
        "最近回答",
    ]

    await engine.dispose()


@pytest.mark.asyncio
async def test_compactor_failure_preserves_all_raw_items(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'memory-failure.db').as_posix()}",
        poolclass=NullPool,
    )
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

    sdk_session = AgentSessionFactory(
        engine=engine,
        recent_limit=10,
    ).create(session_id)
    await sdk_session.add_items(
        [{"role": "user", "content": f"消息 {index}"} for index in range(4)]
    )

    class FailingAgent:
        async def summarize(self, **kwargs):
            raise RuntimeError("摘要模型不可用")

    async with factory() as session:
        compactor = ChatMemoryCompactor(
            session_repository=ChatSessionRepository(session),
            memory_repository=AgentMemoryRepository(session),
            summary_agent=FailingAgent(),  # type: ignore[arg-type]
            session=session,
            trigger_items=4,
            keep_recent_items=2,
            input_max_chars=4000,
            context_recent_limit=10,
        )
        with pytest.raises(RuntimeError, match="摘要模型不可用"):
            await compactor.compact_if_needed(
                session_id=session_id,
                user_id=user_id,
            )
        await session.rollback()
        records = await AgentMemoryRepository(session).list_for_session(
            str(session_id)
        )
        loaded = await session.get(ChatSession, session_id)

        assert len(records) == 4
        assert loaded is not None
        assert loaded.summary is None
        assert loaded.summary_through_agent_message_id == 0

    await engine.dispose()
