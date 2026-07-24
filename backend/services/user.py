"""用户业务服务。"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.repositories.user import UserRepository
from backend.services.exceptions import UserNotFoundError


class UserService:
    """编排用户业务规则和事务边界。"""

    _UPDATABLE_FIELDS = frozenset({"display_name"})

    def __init__(
        self,
        repository: UserRepository,
        session: AsyncSession,
    ):
        self._repository = repository
        self._session = session

    async def create_guest(self, display_name: str | None = None) -> User:
        """创建匿名用户。

        用户 ID 永远由服务端生成，客户端不能指定，避免伪造其他用户身份。
        """
        user = User(
            user_type="guest",
            display_name=display_name,
            is_active=True,
        )
        await self._repository.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def get_user(self, user_id: uuid.UUID) -> User:
        """读取用户；不存在时抛出业务异常。"""
        user = await self._repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(str(user_id))
        return user

    async def update_profile(
        self,
        user_id: uuid.UUID,
        values: Mapping[str, Any],
    ) -> User:
        """更新用户资料，目前只开放昵称字段。"""
        user = await self.get_user(user_id)
        safe_values = {
            key: value
            for key, value in values.items()
            if key in self._UPDATABLE_FIELDS
        }
        if safe_values:
            await self._repository.update(user, safe_values)
            await self._session.commit()
            await self._session.refresh(user)
        return user
