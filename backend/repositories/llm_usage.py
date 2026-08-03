"""LLM 用量记录数据访问。"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.llm_usage import LLMUsageRecord


class LLMUsageRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, record: LLMUsageRecord) -> LLMUsageRecord:
        self._session.add(record)
        await self._session.flush()
        return record
