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
    """
    读取会话摘要和最近消息，组装存储无关的 ChatTurnInput。

    职责：
    - 验证会话归属
    - 过滤有效的历史消息（已完成且未被摘要覆盖）
    - 转换消息格式，并校验数据完整性
    - 组装 Agent 输入对象
    """

    def __init__(
        self,
        *,
        session_repository: ChatSessionRepository,
        message_repository: ChatMessageRepository,
        recent_message_limit: int = 50,
    ):
        """
        构造上下文构建器。

        :param session_repository: 会话存储仓库，用于获取会话摘要等信息
        :param message_repository: 消息存储仓库，用于获取历史消息
        :param recent_message_limit: 每次从数据库读取的最新消息数量上限，
                                     实际还会根据摘要序列进一步过滤
        """
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

        :param user_id: 当前用户 ID
        :param session_id: 当前会话 ID
        :param user_message: 本轮用户输入的文本
        :param model: 可选的模型名称，若为 None 则使用会话中保存的默认模型

        :return: 组装好的 ChatTurnInput 对象

        :raises ChatSessionContextNotFoundError: 会话不存在或不属于该用户
        :raises InvalidChatHistoryError: 历史消息数据格式不合法
        """
        # 1. 获取会话信息（同时校验所有权）
        chat_session = await self._session_repository.get_for_user(
            session_id,
            user_id,
        )
        if chat_session is None:
            raise ChatSessionContextNotFoundError(
                f"会话 {session_id} 不存在"
            )
        # 2. 读取该会话最近的消息（按时间倒序，取最近 limit 条）
        stored_messages = (
            await self._message_repository.list_recent_for_session(
                session_id,
                user_id,
                limit=self._recent_message_limit,
            )
        )
        # 3. 过滤并转换消息为 Agent 所需的上下文消息列表
        context_messages: list[ChatContextMessage] = []
        for message in stored_messages:
            # 3.1 只保留状态为 'completed' 的消息（未完成或已取消的不进入模型上下文）
            if message.status != "completed":
                continue
            # 3.2 跳过已被会话摘要覆盖的旧消息（摘要已包含其信息）
            if message.sequence <= chat_session.summary_through_sequence:
                continue
            # 3.3 将数据库消息转换为 Pydantic 模型，若字段不符合则抛出异常
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

        # 4. 组装最终的 ChatTurnInput
        #    注意：active_divination_id 直接取自会话，model 参数若未指定则用会话默认模型
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
