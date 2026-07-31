"""Agents SDK 原始 Session Item 的长期记忆数据访问。"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_session import AgentMessageRecord


class AgentMemoryRepository:
    """只管理 SDK Item；业务会话所有权由 ChatSessionRepository 校验。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_for_session(
        self,
        session_id: str,
    ) -> list[AgentMessageRecord]:
        result = await self._session.scalars(
            select(AgentMessageRecord)
            .where(AgentMessageRecord.session_id == session_id)
            .order_by(AgentMessageRecord.id.asc())
        )
        return list(result.all())

    async def delete_through(
        self,
        *,
        session_id: str,
        through_id: int,
    ) -> int:
        """删除已经被长期摘要覆盖的 SDK Item。"""
        result = await self._session.execute(
            delete(AgentMessageRecord).where(
                AgentMessageRecord.session_id == session_id,
                AgentMessageRecord.id <= through_id,
            )
        )
        return result.rowcount or 0
