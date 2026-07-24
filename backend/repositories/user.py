"""用户数据访问层。"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User


class UserRepository:
    """封装 User 的数据库读写，不承载业务规则和 HTTP 语义。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """按主键读取用户。"""
        return await self._session.get(User, user_id)

    async def add(self, user: User) -> User:
        """新增用户并 flush，使主键和默认字段立即可用。"""
        self._session.add(user)
        await self._session.flush()
        return user

    async def update(self, user: User, values: Mapping[str, Any]) -> User:
        """更新白名单字段并 flush。

        白名单由 Service 层控制，Repository 只负责把已确认的值写入 Model。
        """
        for field, value in values.items():
            setattr(user, field, value)
        await self._session.flush()
        return user
