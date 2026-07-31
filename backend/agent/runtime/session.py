"""Agents SDK SQLAlchemySession 工厂。"""
from __future__ import annotations

import uuid

from agents.extensions.memory import SQLAlchemySession
from agents.memory import Session, SessionSettings
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.agent.memory.session import MemoryAwareSession


class AgentSessionFactory:
    """用业务 ChatSession ID 创建 SDK 原生数据库会话。"""

    def __init__(
        self,
        *,
        engine: AsyncEngine,
        recent_limit: int = 50,
        memory_enabled: bool = False,
    ):
        if recent_limit < 1:
            raise ValueError("recent_limit 必须大于等于 1")
        self._engine = engine
        self._recent_limit = recent_limit
        self._memory_enabled = memory_enabled
        self._session_settings = SessionSettings(limit=recent_limit)

    def create(
        self,
        session_id: uuid.UUID,
        *,
        memory_summary: str | None = None,
    ) -> Session:
        underlying = SQLAlchemySession(
            str(session_id),
            engine=self._engine,
            create_tables=False,
            session_settings=(
                SessionSettings(limit=None)
                if self._memory_enabled
                else self._session_settings
            ),
        )
        if not self._memory_enabled:
            return underlying
        return MemoryAwareSession(
            underlying=underlying,
            memory_summary=memory_summary,
            recent_limit=self._recent_limit,
        )

    async def clear(self, session_id: uuid.UUID) -> None:
        underlying = SQLAlchemySession(
            str(session_id),
            engine=self._engine,
            create_tables=False,
            session_settings=self._session_settings,
        )
        await underlying.clear_session()
