"""聊天会话业务服务。"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.context_builder import ChatContextBuilder
from backend.agent.context_summarizer import ChatContextSummarizer
from backend.agent.react_runner import ReActRunner
from backend.models.chat_message import ChatMessage
from backend.models.chat_session import ChatSession
from backend.models.user import utc_now
from backend.repositories.chat_message import ChatMessageRepository
from backend.repositories.chat_session import ChatSessionRepository
from backend.repositories.divination import DivinationRepository
from backend.schema.agent import ChatEvent, ChatEventType
from backend.schema.api.chat import (
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionResponse,
)
from backend.services.exceptions import (
    ChatDivinationOwnershipError,
    ChatSessionArchivedError,
    ChatSessionNotFoundError,
)
from backend.utils.logger import logger


class ChatService:
    """管理会话、消息持久化和一次完整的流式 ReAct 对话。"""

    _UPDATABLE_FIELDS = frozenset(
        {"title", "status", "active_divination_id", "model"}
    )

    def __init__(
        self,
        *,
        session_repository: ChatSessionRepository,
        message_repository: ChatMessageRepository,
        divination_repository: DivinationRepository,
        context_builder: ChatContextBuilder,
        runner: ReActRunner,
        summarizer: ChatContextSummarizer,
        session: AsyncSession,
    ):
        self._session_repository = session_repository
        self._message_repository = message_repository
        self._divination_repository = divination_repository
        self._context_builder = context_builder
        self._runner = runner
        self._summarizer = summarizer
        self._session = session

    async def create_session(
        self,
        payload: ChatSessionCreate,
        user_id: uuid.UUID,
    ) -> ChatSessionResponse:
        await self._ensure_divination_owned(
            payload.active_divination_id,
            user_id,
        )
        chat_session = ChatSession(
            user_id=user_id,
            title=payload.title,
            active_divination_id=payload.active_divination_id,
            model=payload.model,
        )
        await self._session_repository.add(chat_session)
        await self._session.commit()
        await self._session.refresh(chat_session)
        return ChatSessionResponse.model_validate(chat_session)

    async def list_sessions(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChatSessionResponse]:
        rows = await self._session_repository.list_for_user(
            user_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return [
            ChatSessionResponse.model_validate(row)
            for row in rows
        ]

    async def get_session(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatSessionResponse:
        return ChatSessionResponse.model_validate(
            await self._get_session_model(session_id, user_id)
        )

    async def update_session(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        values: Mapping[str, Any],
    ) -> ChatSessionResponse:
        chat_session = await self._get_session_model(session_id, user_id)
        safe_values = {
            key: value
            for key, value in values.items()
            if key in self._UPDATABLE_FIELDS
        }
        if "active_divination_id" in safe_values:
            await self._ensure_divination_owned(
                safe_values["active_divination_id"],
                user_id,
            )
        if safe_values:
            await self._session_repository.update(
                chat_session,
                safe_values,
            )
            await self._session.commit()
            await self._session.refresh(chat_session)
        return ChatSessionResponse.model_validate(chat_session)

    async def delete_session(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        chat_session = await self._get_session_model(session_id, user_id)
        await self._session_repository.delete(chat_session)
        await self._session.commit()

    async def list_messages(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        after_sequence: int = 0,
        limit: int = 100,
        recent: bool = False,
    ) -> list[ChatMessageResponse]:
        await self._get_session_model(session_id, user_id)
        if recent:
            rows = await self._message_repository.list_recent_for_session(
                session_id,
                user_id,
                limit=limit,
            )
        else:
            rows = await self._message_repository.list_for_session(
                session_id,
                user_id,
                after_sequence=after_sequence,
                limit=limit,
            )
        return [
            ChatMessageResponse.model_validate(row)
            for row in rows
        ]

    async def ensure_can_chat(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """在返回 StreamingResponse 前完成可转为 HTTP 状态码的校验。"""
        chat_session = await self._get_session_model(session_id, user_id)
        if chat_session.status != "active":
            raise ChatSessionArchivedError(str(session_id))

    async def stream_reply(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        user_message: str,
        model: str | None = None,
    ) -> AsyncIterator[ChatEvent]:
        """持久化用户输入，执行 Agent，并逐事件保存可观察结果。"""
        chat_session = await self._get_session_model(session_id, user_id)
        if chat_session.status != "active":
            raise ChatSessionArchivedError(str(session_id))

        # 必须先构建旧上下文，再把本轮用户消息写入数据库，避免重复注入。
        turn_input = await self._context_builder.build(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            model=model,
        )
        await self._append_message(
            chat_session,
            user_id,
            role="user",
            content=turn_input.user_message,
            divination_id=chat_session.active_divination_id,
        )
        updates: dict[str, Any] = {"last_message_at": utc_now()}
        if chat_session.title is None:
            updates["title"] = turn_input.user_message[:100]
        await self._session_repository.update(chat_session, updates)
        await self._session.commit()

        visible_chunks: list[str] = []
        terminal_event_seen = False
        try:
            async for event in self._runner.run(turn_input):
                if event.event_type == ChatEventType.TEXT_DELTA:
                    visible_chunks.append(event.content or "")
                elif event.event_type == ChatEventType.TOOL_CALL_STARTED:
                    await self._persist_tool_call(
                        chat_session,
                        user_id,
                        event,
                    )
                elif event.event_type in {
                    ChatEventType.TOOL_CALL_COMPLETED,
                    ChatEventType.TOOL_CALL_FAILED,
                }:
                    await self._persist_tool_result(
                        chat_session,
                        user_id,
                        event,
                    )
                elif event.event_type == ChatEventType.MESSAGE_COMPLETED:
                    await self._append_message(
                        chat_session,
                        user_id,
                        role="assistant",
                        content=event.content,
                        divination_id=chat_session.active_divination_id,
                    )
                    await self._session_repository.update(
                        chat_session,
                        {"last_message_at": utc_now()},
                    )
                    await self._session.commit()
                    terminal_event_seen = True
                elif event.event_type == ChatEventType.ERROR:
                    await self._persist_failed_assistant(
                        chat_session,
                        user_id,
                        "".join(visible_chunks) or event.content,
                        status="failed",
                        error_event=event,
                    )
                    terminal_event_seen = True

                yield event

            if terminal_event_seen:
                await self._try_summarize(user_id, session_id)
        except asyncio.CancelledError:
            if not terminal_event_seen:
                await self._persist_failed_assistant(
                    chat_session,
                    user_id,
                    "".join(visible_chunks) or "生成已取消",
                    status="cancelled",
                )
            raise
        except Exception:
            await self._session.rollback()
            logger.exception("Chatbot 流式执行或消息持久化失败")
            raise

    async def _persist_tool_call(
        self,
        chat_session: ChatSession,
        user_id: uuid.UUID,
        event: ChatEvent,
    ) -> None:
        await self._append_message(
            chat_session,
            user_id,
            role="assistant",
            message_type="tool_call",
            tool_name=event.tool_name,
            tool_call_id=event.tool_call_id,
            payload=event.tool_arguments,
            divination_id=chat_session.active_divination_id,
        )
        await self._session.commit()

    async def _persist_tool_result(
        self,
        chat_session: ChatSession,
        user_id: uuid.UUID,
        event: ChatEvent,
    ) -> None:
        result = event.tool_result
        if result is None:
            raise RuntimeError("工具完成事件缺少 ToolResult")

        new_divination_id: str | None = None
        if isinstance(result.data, dict):
            candidate = result.data.get("divination_id")
            if isinstance(candidate, str):
                owned = await self._divination_repository.get_for_user(
                    candidate,
                    user_id,
                )
                if owned is not None:
                    new_divination_id = candidate
                    await self._session_repository.update(
                        chat_session,
                        {"active_divination_id": candidate},
                    )

        await self._append_message(
            chat_session,
            user_id,
            role="tool",
            message_type="tool_result",
            content=result.model_content,
            tool_name=event.tool_name,
            tool_call_id=event.tool_call_id,
            payload=result.model_dump(mode="json"),
            divination_id=(
                new_divination_id or chat_session.active_divination_id
            ),
        )
        await self._session.commit()

    async def _persist_failed_assistant(
        self,
        chat_session: ChatSession,
        user_id: uuid.UUID,
        content: str | None,
        *,
        status: str,
        error_event: ChatEvent | None = None,
    ) -> None:
        payload = (
            {
                "error_code": error_event.error_code,
                "retryable": error_event.retryable,
            }
            if error_event is not None
            else None
        )
        await self._append_message(
            chat_session,
            user_id,
            role="assistant",
            content=content,
            status=status,
            payload=payload,
            divination_id=chat_session.active_divination_id,
        )
        await self._session_repository.update(
            chat_session,
            {"last_message_at": utc_now()},
        )
        await self._session.commit()

    async def _append_message(
        self,
        chat_session: ChatSession,
        user_id: uuid.UUID,
        *,
        role: str,
        message_type: str = "text",
        content: str | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        payload: Any = None,
        status: str = "completed",
        divination_id: str | None = None,
    ) -> ChatMessage:
        sequence = (
            await self._session_repository.reserve_next_message_sequence(
                chat_session.id,
                user_id,
            )
        )
        if sequence is None:
            raise ChatSessionNotFoundError(str(chat_session.id))
        message = ChatMessage(
            session_id=chat_session.id,
            divination_id=divination_id,
            sequence=sequence,
            role=role,
            message_type=message_type,
            content=content,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            payload=payload,
            status=status,
        )
        added = await self._message_repository.add_for_user(
            message,
            user_id,
        )
        if added is None:
            raise ChatSessionNotFoundError(str(chat_session.id))
        return added

    async def _try_summarize(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        try:
            changed = await self._summarizer.maybe_summarize(
                user_id=user_id,
                session_id=session_id,
            )
            if changed:
                await self._session.commit()
        except Exception:
            await self._session.rollback()
            logger.exception("Chatbot 上下文摘要失败，本轮回答仍保留")

    async def _get_session_model(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatSession:
        chat_session = await self._session_repository.get_for_user(
            session_id,
            user_id,
        )
        if chat_session is None:
            raise ChatSessionNotFoundError(str(session_id))
        return chat_session

    async def _ensure_divination_owned(
        self,
        divination_id: str | None,
        user_id: uuid.UUID,
    ) -> None:
        if divination_id is None:
            return
        owned = await self._divination_repository.get_for_user(
            divination_id,
            user_id,
        )
        if owned is None:
            raise ChatDivinationOwnershipError(divination_id)
