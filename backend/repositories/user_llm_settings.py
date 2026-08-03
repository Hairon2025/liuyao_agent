"""用户 LLM 设置数据访问。"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user_llm_settings import UserLLMSettings


class UserLLMSettingsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_for_user(
        self,
        user_id: uuid.UUID,
    ) -> UserLLMSettings | None:
        return await self._session.scalar(
            select(UserLLMSettings).where(
                UserLLMSettings.user_id == user_id
            )
        )

    async def add(self, settings: UserLLMSettings) -> UserLLMSettings:
        self._session.add(settings)
        await self._session.flush()
        return settings

    async def update(
        self,
        settings: UserLLMSettings,
        values: Mapping[str, Any],
    ) -> UserLLMSettings:
        for key, value in values.items():
            setattr(settings, key, value)
        await self._session.flush()
        return settings

    async def delete(self, settings: UserLLMSettings) -> None:
        await self._session.delete(settings)
        await self._session.flush()
