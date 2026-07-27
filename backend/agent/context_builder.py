"""从持久化会话构建 Chatbot 单轮输入。"""
from __future__ import annotations

import uuid

from pydantic import ValidationError

from backend.repositories.chat_message import ChatMessageRepository
from backend.repositories.chat_session import ChatSessionRepository
from backend.schema.agent import ChatContextMessage, ChatTurnInput


class ChatContextBuildError(Exception):
    """构建 Agent 上下文失败。"""


class ChatSessionContextNotFoundError(ChatContextBuildError):
    """会话不存在或不属于当前用户。"""


class InvalidChatHistoryError(ChatContextBuildError):
    """数据库中的历史消息不符合 Agent 协议。"""


class ChatContextBuilder:
    """读取会话摘要和最近消息，组装存储无关的 ChatTurnInput。"""

    def __init__(
        self,
        *,
        session_repository: ChatSessionRepository,
        message_repository: ChatMessageRepository,
        recent_message_limit: int = 50,
    ):
        if recent_message_limit < 1:
            raise ValueError("recent_message_limit 必须大于等于 1")
        self._session_repository = session_repository
        self._message_repository = message_repository
        self._recent_message_limit = recent_message_limit

    async def build(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        user_message: str,
        model: str | None = None,
    ) -> ChatTurnInput:
        """构建一次 Agent 输入。

        `user_message` 表示本轮尚未进入历史窗口的新消息。未来 ChatService
        应先构建上下文，再持久化该消息，避免在 recent_messages 中重复出现。
        """
        chat_session = await self._session_repository.get_for_user(
            session_id,
            user_id,
        )
        if chat_session is None:
            raise ChatSessionContextNotFoundError(
                f"会话 {session_id} 不存在"
            )

        stored_messages = (
            await self._message_repository.list_recent_for_session(
                session_id,
                user_id,
                limit=self._recent_message_limit,
            )
        )
        context_messages: list[ChatContextMessage] = []
        for message in stored_messages:
            # 未完成或已取消的占位消息不进入下一轮模型上下文。
            if message.status != "completed":
                continue
            if message.sequence <= chat_session.summary_through_sequence:
                continue
            try:
                context_messages.append(
                    ChatContextMessage(
                        id=message.id,
                        sequence=message.sequence,
                        role=message.role,
                        message_type=message.message_type,
                        content=message.content,
                        tool_name=message.tool_name,
                        tool_call_id=message.tool_call_id,
                        payload=message.payload,
                        status=message.status,
                    )
                )
            except ValidationError as exc:
                raise InvalidChatHistoryError(
                    f"历史消息 {message.id} 不符合 Agent 协议"
                ) from exc

        return ChatTurnInput(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            session_summary=chat_session.summary,
            summary_through_sequence=(
                chat_session.summary_through_sequence
            ),
            recent_messages=context_messages,
            active_divination_id=chat_session.active_divination_id,
            # 仅 None 表示不覆盖；空白字符串交给协议模型明确拒绝。
            model=chat_session.model if model is None else model,
        )
