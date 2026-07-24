"""卦例数据访问层。"""
from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.divination import Divination


class DivinationRepository:
    """封装卦例数据库读写，所有读取均显式限定用户。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _owned_query(
        divination_id: str,
        user_id: uuid.UUID,
    ) -> Select[tuple[Divination]]:
        return select(Divination).where(
            Divination.id == divination_id,
            Divination.user_id == user_id,
        )

    async def add(self, divination: Divination) -> Divination:
        """新增卦例并 flush。"""
        self._session.add(divination)
        await self._session.flush()
        return divination

    async def get_for_user(
        self,
        divination_id: str,
        user_id: uuid.UUID,
    ) -> Divination | None:
        """读取属于指定用户的卦例。"""
        result = await self._session.execute(
            self._owned_query(divination_id, user_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[Divination]:
        """按创建时间倒序读取用户的全部卦例。"""
        result = await self._session.execute(
            select(Divination)
            .where(Divination.user_id == user_id)
            .order_by(Divination.created_at.desc(), Divination.id.desc())
        )
        return result.scalars().all()

    async def update(
        self,
        divination: Divination,
        values: Mapping[str, Any],
    ) -> Divination:
        """更新 Service 层已校验的字段。"""
        for field, value in values.items():
            setattr(divination, field, value)
        await self._session.flush()
        return divination

    async def delete(self, divination: Divination) -> None:
        """删除指定卦例。"""
        await self._session.delete(divination)
        await self._session.flush()
