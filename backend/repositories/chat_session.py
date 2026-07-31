"""聊天会话数据访问层。"""
from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Select, select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.chat_session import ChatSession


class ChatSessionRepository:
    """封装聊天会话读写，并在所有读取中限定用户所有权。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _owned_query(
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Select[tuple[ChatSession]]:
        return select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )

    async def add(self, chat_session: ChatSession) -> ChatSession:
        """新增会话并 flush，使默认主键和计数器立即可用。"""
        self._session.add(chat_session)
        await self._session.flush()
        return chat_session

    async def get_for_user(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatSession | None:
        """读取属于指定用户的会话。"""
        result = await self._session.execute(
            self._owned_query(session_id, user_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[ChatSession]:
        """按最后消息时间倒序分页读取用户会话。"""
        query = select(ChatSession).where(ChatSession.user_id == user_id)
        if status is not None:
            query = query.where(ChatSession.status == status)
        result = await self._session.execute(
            query
            .order_by(
                ChatSession.last_message_at.desc(),
                ChatSession.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def update(
        self,
        chat_session: ChatSession,
        values: Mapping[str, Any],
    ) -> ChatSession:
        """更新 Service 层已确认的字段并 flush。"""
        for field, value in values.items():
            setattr(chat_session, field, value)
        await self._session.flush()
        return chat_session

    async def delete(self, chat_session: ChatSession) -> None:
        """删除会话；消息由数据库外键级联删除。"""
        await self._session.delete(chat_session)
        await self._session.flush()

    async def reserve_next_message_sequence(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> int | None:
        """原子预留下一条消息序号。

        返回 ``None`` 表示会话不存在或不属于指定用户。计数器更新和消息写入
        应处于同一事务中；后续任一步失败时回滚即可归还该序号。
        """
        result = await self._session.execute(
            sql_update(ChatSession)
            .where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
            )
            .values(
                next_message_sequence=(
                    ChatSession.next_message_sequence + 1
                )
            )
            .returning(ChatSession.next_message_sequence)
        )
        next_sequence = result.scalar_one_or_none()
        if next_sequence is None:
            return None
        return next_sequence - 1

    async def update_summary_if_boundary_matches(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        expected_agent_message_id: int,
        summary: str,
        through_agent_message_id: int,
        summary_updated_at: datetime,
    ) -> bool:
        """按摘要边界做乐观更新，避免同一会话被并发压缩两次。"""
        result = await self._session.execute(
            sql_update(ChatSession)
            .where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
                ChatSession.summary_through_agent_message_id
                == expected_agent_message_id,
            )
            .values(
                summary=summary,
                summary_through_agent_message_id=through_agent_message_id,
                summary_updated_at=summary_updated_at,
            )
        )
        return result.rowcount == 1
