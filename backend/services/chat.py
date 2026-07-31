"""聊天会话业务服务。"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.chat_orchestrator import ChatAgentOrchestrator
from backend.agent.runtime.context import AgentRunContext
from backend.agent.runtime.session import AgentSessionFactory
from backend.agent.suggested_question_agent import SuggestedQuestionAgent
from backend.models.chat_message import ChatMessage
from backend.models.chat_session import ChatSession
from backend.models.user import utc_now
from backend.repositories.chat_message import ChatMessageRepository
from backend.repositories.chat_session import ChatSessionRepository
from backend.repositories.divination import DivinationRepository
from backend.schema.agent import (
    ChatEvent,
    ChatEventType,
    SuggestedQuestionsPayload,
)
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
from backend.services.chat_divination_workflow import ChatDivinationWorkflow
from backend.services.divination import DivinationService
from backend.utils.logger import logger


class ChatService:
    """管理业务会话，并用 Agents SDK 执行一次流式对话。"""

    _UPDATABLE_FIELDS = frozenset(
        {"title", "status", "active_divination_id", "model"}
    )

    def __init__(
        self,
        *,
        session_repository: ChatSessionRepository,
        message_repository: ChatMessageRepository,
        divination_repository: DivinationRepository,
        chatbot: ChatAgentOrchestrator,
        agent_session_factory: AgentSessionFactory,
        divination_service: DivinationService,
        chat_divination_workflow: ChatDivinationWorkflow,
        session: AsyncSession,
        suggested_question_agent: SuggestedQuestionAgent | None = None,
    ):
        self._session_repository = session_repository
        self._message_repository = message_repository
        self._divination_repository = divination_repository
        self._chatbot = chatbot
        self._agent_session_factory = agent_session_factory
        self._divination_service = divination_service
        self._chat_divination_workflow = chat_divination_workflow
        self._session = session
        self._suggested_question_agent = suggested_question_agent

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
        # SDK 会话表不依赖 ORM 级联，先显式清理 Agent 历史。
        await self._agent_session_factory.clear(session_id)
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

        message_text = user_message.strip()
        await self._append_message(
            chat_session,
            user_id=user_id,
            role="user",
            content=message_text,
            divination_id=chat_session.active_divination_id,
        )
        updates: dict[str, Any] = {"last_message_at": utc_now()}
        if chat_session.title is None:
            updates["title"] = message_text[:100]
        await self._session_repository.update(chat_session, updates)
        await self._session.commit()

        run_context = AgentRunContext(
            user_id=user_id,
            session_id=session_id,
            divination_service=self._divination_service,
            chat_divination_workflow=self._chat_divination_workflow,
            active_divination_id=chat_session.active_divination_id,
            workflow_state=chat_session.workflow_state,
        )
        sdk_session = self._agent_session_factory.create(session_id)
        visible_chunks: list[str] = []
        # SDK 会在后台执行 Function Tool，并先发出 tool_call_started。
        # 工具与本 Service 共享请求级 AsyncSession，因此工具完成前不能在这里
        # flush；先缓存开始事件，收到结果后再按调用、结果顺序持久化。
        pending_tool_calls: dict[str, ChatEvent] = {}
        terminal_event_seen = False
        completed_assistant: ChatMessage | None = None
        suggestions_allowed = True
        try:
            async for event in self._chatbot.stream(
                user_message=message_text,
                context=run_context,
                session=sdk_session,
                model=model or chat_session.model,
            ):
                if event.event_type == ChatEventType.TEXT_DELTA:
                    visible_chunks.append(event.content or "")
                elif event.event_type == ChatEventType.TOOL_CALL_STARTED:
                    assert event.tool_call_id is not None
                    pending_tool_calls[event.tool_call_id] = event
                elif event.event_type in {
                    ChatEventType.TOOL_CALL_COMPLETED,
                    ChatEventType.TOOL_CALL_FAILED,
                }:
                    assert event.tool_call_id is not None
                    started = pending_tool_calls.pop(
                        event.tool_call_id,
                        None,
                    )
                    if started is not None:
                        await self._persist_tool_call(
                            chat_session,
                            user_id,
                            started,
                        )
                    await self._persist_tool_result(
                        chat_session,
                        user_id,
                        event,
                    )
                    if (
                        event.tool_result is not None
                        and isinstance(event.tool_result.data, dict)
                    ):
                        candidate = event.tool_result.data.get(
                            "divination_id"
                        )
                        if isinstance(candidate, str):
                            run_context.active_divination_id = candidate
                    if (
                        event.tool_result is not None
                        and isinstance(event.tool_result.data, dict)
                        and event.tool_result.data.get("status")
                        == "needs_input"
                    ):
                        suggestions_allowed = False
                elif event.event_type == ChatEventType.MESSAGE_COMPLETED:
                    await self._persist_pending_tool_calls(
                        chat_session,
                        user_id,
                        pending_tool_calls,
                    )
                    completed_assistant = await self._append_message(
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
                    await self._persist_pending_tool_calls(
                        chat_session,
                        user_id,
                        pending_tool_calls,
                    )
                    await self._persist_failed_assistant(
                        chat_session,
                        user_id,
                        "".join(visible_chunks) or event.content,
                        status="failed",
                        error_event=event,
                    )
                    terminal_event_seen = True

                yield event

            if (
                terminal_event_seen
                and completed_assistant is not None
                and suggestions_allowed
                and run_context.active_divination_id is not None
            ):
                suggestion_event = await self._generate_suggestions(
                    chat_session=chat_session,
                    user_id=user_id,
                    user_message=message_text,
                    assistant_message=completed_assistant,
                    divination_id=run_context.active_divination_id,
                )
                if suggestion_event is not None:
                    yield suggestion_event
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

    async def _generate_suggestions(
        self,
        *,
        chat_session: ChatSession,
        user_id: uuid.UUID,
        user_message: str,
        assistant_message: ChatMessage,
        divination_id: str,
    ) -> ChatEvent | None:
        """生成辅助追问；失败只记日志，不影响已经完成的主回答。"""
        if (
            self._suggested_question_agent is None
            or not assistant_message.content
        ):
            return None
        # rollback 会让 ORM 实例过期。提前保存纯值，异常日志中不要再次触发
        # chat_session 属性的懒加载，否则异步环境会额外抛出 MissingGreenlet。
        chat_session_id = chat_session.id
        try:
            generated = await self._suggested_question_agent.generate(
                user_message=user_message,
                assistant_answer=assistant_message.content,
            )
            if not generated.questions:
                return None
            payload = SuggestedQuestionsPayload(
                source_message_id=assistant_message.id,
                questions=generated.questions,
            )
            await self._append_message(
                chat_session,
                user_id,
                role="assistant",
                message_type="suggestions",
                payload=payload.model_dump(mode="json"),
                divination_id=divination_id,
            )
            await self._session.commit()
            return ChatEvent(
                event_type=ChatEventType.SUGGESTIONS,
                source_message_id=assistant_message.id,
                questions=generated.questions,
            )
        except Exception:
            await self._session.rollback()
            logger.exception(
                "会话 %s 的追问建议生成或保存失败",
                chat_session_id,
            )
            return None

    async def _persist_pending_tool_calls(
        self,
        chat_session: ChatSession,
        user_id: uuid.UUID,
        pending: dict[str, ChatEvent],
    ) -> None:
        """在 Agent 已结束工具执行后补存没有结果事件的工具调用。"""
        for event in pending.values():
            await self._persist_tool_call(
                chat_session,
                user_id,
                event,
            )
        pending.clear()

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
