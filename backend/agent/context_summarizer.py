"""Chatbot 会话上下文压缩。"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from backend.agent.model import ChatModelAdapter
from backend.models.chat_message import ChatMessage
from backend.repositories.chat_message import ChatMessageRepository
from backend.repositories.chat_session import ChatSessionRepository
from backend.schema.agent import (
    ChatRole,
    ModelFinishReason,
    ModelMessage,
    ModelRequest,
    ModelStreamEventType,
)

_PROMPT_FILE = Path(__file__).parent / "prompt" / "chat_summary.txt"


class ContextSummaryError(RuntimeError):
    """模型未能生成有效上下文摘要。"""


class ChatContextSummarizer:
    """达到消息阈值时，把较旧消息合并进会话摘要。"""

    def __init__(
        self,
        *,
        session_repository: ChatSessionRepository,
        message_repository: ChatMessageRepository,
        model_adapter: ChatModelAdapter,
        trigger_messages: int = 40,
        keep_recent: int = 12,
    ):
        if trigger_messages < 2:
            raise ValueError("trigger_messages 必须大于等于 2")
        if keep_recent < 1 or keep_recent >= trigger_messages:
            raise ValueError(
                "keep_recent 必须大于等于 1 且小于 trigger_messages"
            )
        self._session_repository = session_repository
        self._message_repository = message_repository
        self._model_adapter = model_adapter
        self._trigger_messages = trigger_messages
        self._keep_recent = keep_recent
        self._instructions = _PROMPT_FILE.read_text(encoding="utf-8")

    async def maybe_summarize(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> bool:
        """必要时更新摘要；未达到阈值返回 False。"""
        chat_session = await self._session_repository.get_for_user(
            session_id,
            user_id,
        )
        if chat_session is None:
            return False

        messages = await self._message_repository.list_for_session(
            session_id,
            user_id,
            after_sequence=chat_session.summary_through_sequence,
            limit=self._trigger_messages * 2,
        )
        completed = [
            message for message in messages if message.status == "completed"
        ]
        if len(completed) < self._trigger_messages:
            return False

        to_summarize = completed[:-self._keep_recent]
        if not to_summarize:
            return False

        history = "\n".join(
            self._format_message(message) for message in to_summarize
        )
        previous_summary = chat_session.summary or "（无旧摘要）"
        request = ModelRequest(
            instructions=self._instructions,
            model=chat_session.model,
            messages=[
                ModelMessage(
                    role=ChatRole.USER,
                    content=(
                        f"旧摘要：\n{previous_summary}\n\n"
                        f"需要继续压缩的消息：\n{history}"
                    ),
                )
            ],
        )

        chunks: list[str] = []
        finish_reason: ModelFinishReason | None = None
        async for event in self._model_adapter.stream(request):
            if event.event_type == ModelStreamEventType.TEXT_DELTA:
                chunks.append(event.delta or "")
            elif event.event_type == ModelStreamEventType.TOOL_CALL:
                raise ContextSummaryError("摘要模型不应调用工具")
            elif event.event_type == ModelStreamEventType.STEP_COMPLETED:
                finish_reason = event.finish_reason

        summary = "".join(chunks).strip()
        if finish_reason != ModelFinishReason.STOP or not summary:
            raise ContextSummaryError("摘要模型没有正常生成完整摘要")

        await self._session_repository.update(
            chat_session,
            {
                "summary": summary,
                "summary_through_sequence": to_summarize[-1].sequence,
            },
        )
        return True

    @staticmethod
    def _format_message(message: ChatMessage) -> str:
        payload = (
            json.dumps(message.payload, ensure_ascii=False)
            if message.payload is not None
            else ""
        )
        return (
            f"[sequence={message.sequence}] "
            f"{message.role}/{message.message_type}: "
            f"{message.content or ''} {payload}"
        ).strip()
