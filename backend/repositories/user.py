"""用户数据访问层。"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.chat_session import ChatSession
from backend.models.divination import Divination
from backend.models.llm_usage import LLMUsageRecord
from backend.models.user import User


class UserRepository:
    """封装 User 的数据库读写，不承载业务规则和 HTTP 语义。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """按主键读取用户。"""
        return await self._session.get(User, user_id)

    async def get_by_normalized_username(self, username: str) -> User | None:
        return await self._session.scalar(
            select(User).where(User.username_normalized == username)
        )

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

    async def reassign_owned_resources(
        self,
        source_user_id: uuid.UUID,
        target_user_id: uuid.UUID,
    ) -> None:
        """把来源用户拥有的业务资源批量转移给目标用户。

        当前用于游客登录已有账号时保留游客阶段产生的数据。聊天消息通过
        ``chat_sessions`` 间接归属用户，因此无需单独更新。
        """
        for model in (Divination, ChatSession, LLMUsageRecord):
            await self._session.execute(
                update(model)
                .where(model.user_id == source_user_id)
                .values(user_id=target_user_id)
            )
        await self._session.flush()

    async def delete_guest(self, user_id: uuid.UUID) -> bool:
        """仅删除游客记录，避免调用方误删已注册用户。"""
        result = await self._session.execute(
            delete(User).where(
                User.id == user_id,
                User.user_type == "guest",
            )
        )
        await self._session.flush()
        return result.rowcount == 1
