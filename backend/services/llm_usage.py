"""把 Agents SDK Usage 持久化为不含内容的模型用量记录。"""
from __future__ import annotations

import uuid
from urllib.parse import urlparse

from agents.usage import Usage
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.llm_usage import LLMUsageRecord
from backend.repositories.llm_usage import LLMUsageRepository
from backend.utils.logger import logger


class LLMUsageRecorder:
    def __init__(
        self,
        *,
        user_id: uuid.UUID,
        repository: LLMUsageRepository,
        session: AsyncSession,
    ):
        self._user_id = user_id
        self._repository = repository
        self._session = session

    async def record(
        self,
        *,
        agent_role: str,
        model: str,
        base_url: str,
        duration_ms: int,
        status: str,
        usage: Usage | None = None,
        error_code: str | None = None,
    ) -> None:
        """用量记录失败不能把已经完成的用户回答判为失败。"""
        try:
            await self._repository.add(
                LLMUsageRecord(
                    user_id=self._user_id,
                    agent_role=agent_role,
                    model=model,
                    base_url_host=urlparse(base_url).hostname or "unknown",
                    input_tokens=usage.input_tokens if usage else None,
                    output_tokens=usage.output_tokens if usage else None,
                    total_tokens=usage.total_tokens if usage else None,
                    request_count=usage.requests if usage else None,
                    duration_ms=max(duration_ms, 0),
                    status=status,
                    error_code=error_code,
                )
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            logger.exception("LLM 用量记录保存失败")
