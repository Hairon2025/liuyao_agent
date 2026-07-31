"""Agents SDK SQLAlchemySession 工厂。"""
from __future__ import annotations

import uuid

from agents.extensions.memory import SQLAlchemySession
from agents.memory import SessionSettings
from sqlalchemy.ext.asyncio import AsyncEngine


class AgentSessionFactory:
    """用业务 ChatSession ID 创建 SDK 原生数据库会话。"""

    def __init__(self, *, engine: AsyncEngine, recent_limit: int = 50):
        if recent_limit < 1:
            raise ValueError("recent_limit 必须大于等于 1")
        self._engine = engine
        self._session_settings = SessionSettings(limit=recent_limit)

    def create(self, session_id: uuid.UUID) -> SQLAlchemySession:
        return SQLAlchemySession(
            str(session_id),
            engine=self._engine,
            create_tables=False,
            session_settings=self._session_settings,
        )

    async def clear(self, session_id: uuid.UUID) -> None:
        await self.create(session_id).clear_session()
