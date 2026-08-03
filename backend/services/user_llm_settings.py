"""用户 LLM 设置保存、解密、解析与连接测试。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user_llm_settings import UserLLMSettings
from backend.repositories.user_llm_settings import UserLLMSettingsRepository
from backend.schema.api.llm_settings import (
    LLMConnectionTestResponse,
    UserLLMSettingsResponse,
    UserLLMSettingsUpsert,
)
from backend.services.exceptions import (
    UserLLMSettingsInvalidError,
    UserLLMSettingsRequiredError,
)
from backend.utils.security import CredentialCipher, validate_llm_base_url


@dataclass(frozen=True)
class ResolvedUserLLMConfig:
    api_key: str
    base_url: str
    model: str
    analyst_model: str
    suggestion_model: str
    memory_model: str
    timeout_seconds: float


class UserLLMSettingsService:
    def __init__(
        self,
        *,
        repository: UserLLMSettingsRepository,
        session: AsyncSession,
        encryption_key: str,
        allow_private_base_urls: bool,
    ):
        self._repository = repository
        self._session = session
        self._encryption_key = encryption_key
        self._allow_private = allow_private_base_urls

    async def get(
        self,
        user_id: uuid.UUID,
    ) -> UserLLMSettingsResponse | None:
        settings = await self._repository.get_for_user(user_id)
        return self._response(settings) if settings else None

    async def upsert(
        self,
        user_id: uuid.UUID,
        payload: UserLLMSettingsUpsert,
    ) -> UserLLMSettingsResponse:
        existing = await self._repository.get_for_user(user_id)
        base_url = validate_llm_base_url(
            payload.base_url,
            allow_private=self._allow_private,
        )
        values = payload.model_dump(exclude={"api_key"})
        values["base_url"] = base_url
        values["is_active"] = True
        if payload.api_key is not None:
            cipher = self._cipher()
            values["api_key_ciphertext"] = cipher.encrypt(payload.api_key)
            values["api_key_last4"] = payload.api_key[-4:]

        if existing is None:
            if payload.api_key is None:
                raise ValueError("首次保存 LLM 设置时必须提供 API Key")
            existing = UserLLMSettings(user_id=user_id, **values)
            await self._repository.add(existing)
        else:
            await self._repository.update(existing, values)
        await self._session.commit()
        await self._session.refresh(existing)
        return self._response(existing)

    async def delete(self, user_id: uuid.UUID) -> None:
        settings = await self._repository.get_for_user(user_id)
        if settings is None:
            return
        await self._repository.delete(settings)
        await self._session.commit()

    async def resolve(self, user_id: uuid.UUID) -> ResolvedUserLLMConfig:
        settings = await self._repository.get_for_user(user_id)
        if settings is None or not settings.is_active:
            raise UserLLMSettingsRequiredError()
        try:
            api_key = self._cipher().decrypt(settings.api_key_ciphertext)
        except ValueError as exc:
            raise UserLLMSettingsInvalidError(str(exc)) from exc
        return ResolvedUserLLMConfig(
            api_key=api_key,
            base_url=settings.base_url,
            model=settings.model,
            analyst_model=settings.analyst_model or settings.model,
            suggestion_model=settings.suggestion_model or settings.model,
            memory_model=settings.memory_model or settings.model,
            timeout_seconds=settings.timeout_seconds,
        )

    async def test_connection(
        self,
        user_id: uuid.UUID,
    ) -> LLMConnectionTestResponse:
        config = await self.resolve(user_id)
        client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=min(config.timeout_seconds, 30),
        )
        try:
            await client.models.list()
        except Exception as exc:
            return LLMConnectionTestResponse(
                success=False,
                message=f"连接失败：{type(exc).__name__}",
            )
        finally:
            await client.close()
        return LLMConnectionTestResponse(
            success=True,
            message="模型服务连接成功",
        )

    def _cipher(self) -> CredentialCipher:
        try:
            return CredentialCipher(self._encryption_key)
        except ValueError as exc:
            raise UserLLMSettingsInvalidError(str(exc)) from exc

    @staticmethod
    def _response(settings: UserLLMSettings) -> UserLLMSettingsResponse:
        return UserLLMSettingsResponse(
            base_url=settings.base_url,
            api_key_last4=settings.api_key_last4,
            model=settings.model,
            analyst_model=settings.analyst_model,
            suggestion_model=settings.suggestion_model,
            memory_model=settings.memory_model,
            timeout_seconds=settings.timeout_seconds,
            is_active=settings.is_active,
            created_at=settings.created_at,
            updated_at=settings.updated_at,
        )
