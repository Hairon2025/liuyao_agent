"""聊天消息数据访问层。"""
from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.chat_message import ChatMessage
from backend.models.chat_session import ChatSession


class ChatMessageRepository:
    """封装聊天消息读写，读取时通过所属会话校验用户所有权。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _owned_query(
        user_id: uuid.UUID,
    ) -> Select[tuple[ChatMessage]]:
        return (
            select(ChatMessage)
            .join(
                ChatSession,
                ChatMessage.session_id == ChatSession.id,
            )
            .where(ChatSession.user_id == user_id)
        )

    async def add_for_user(
        self,
        message: ChatMessage,
        user_id: uuid.UUID,
    ) -> ChatMessage | None:
        """校验会话所有权后新增消息并 flush。

        调用方应先使用 ChatSessionRepository 预留序号；两步必须共享同一
        AsyncSession 和事务。返回 ``None`` 表示会话不属于指定用户。
        """
        owned_session_id = await self._session.scalar(
            select(ChatSession.id).where(
                ChatSession.id == message.session_id,
                ChatSession.user_id == user_id,
            )
        )
        if owned_session_id is None:
            return None
        self._session.add(message)
        await self._session.flush()
        return message

    async def get_for_user(
        self,
        message_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatMessage | None:
        """按消息 ID 读取，并校验所属会话的用户。"""
        result = await self._session.execute(
            self._owned_query(user_id).where(ChatMessage.id == message_id)
        )
        return result.scalar_one_or_none()

    async def list_for_session(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> Sequence[ChatMessage]:
        """按序号正序分页读取会话消息。

        `after_sequence` 使用游标语义，比不断增大的 offset 更适合长会话。
        """
        result = await self._session.execute(
            self._owned_query(user_id)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.sequence > after_sequence,
            )
            .order_by(ChatMessage.sequence.asc())
            .limit(limit)
        )
        return result.scalars().all()

    async def list_recent_for_session(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
    ) -> list[ChatMessage]:
        """读取最近若干条消息，并按正常对话顺序返回。"""
        result = await self._session.execute(
            self._owned_query(user_id)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.sequence.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def list_by_tool_call_id_for_user(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        tool_call_id: str,
    ) -> Sequence[ChatMessage]:
        """按顺序读取配对的工具调用及工具结果。"""
        result = await self._session.execute(
            self._owned_query(user_id).where(
                ChatMessage.session_id == session_id,
                ChatMessage.tool_call_id == tool_call_id,
            ).order_by(ChatMessage.sequence.asc())
        )
        return result.scalars().all()

    async def get_suggestions_for_source(
        self,
        source_message_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatMessage | None:
        """读取某条回答已经生成的追问建议。"""
        result = await self._session.execute(
            self._owned_query(user_id).where(
                ChatMessage.source_message_id == source_message_id,
                ChatMessage.message_type == "suggestions",
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_user_before(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        before_sequence: int,
    ) -> ChatMessage | None:
        """读取目标回答之前最近的一条用户文本消息。"""
        result = await self._session.execute(
            self._owned_query(user_id)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.sequence < before_sequence,
                ChatMessage.role == "user",
                ChatMessage.message_type == "text",
            )
            .order_by(ChatMessage.sequence.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        message: ChatMessage,
        values: Mapping[str, Any],
    ) -> ChatMessage:
        """更新消息内容、状态或 Token 统计并 flush。"""
        for field, value in values.items():
            setattr(message, field, value)
        await self._session.flush()
        return message

    async def delete(self, message: ChatMessage) -> None:
        """删除一条已完成所有权校验的消息。"""
        await self._session.delete(message)
        await self._session.flush()
