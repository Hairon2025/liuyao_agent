"""聊天会话业务服务。"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Mapping
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.chat_orchestrator import ChatAgentOrchestrator
from backend.agent.memory.compactor import ChatMemoryCompactor
from backend.agent.runtime.context import AgentRunContext
from backend.agent.runtime.session import AgentSessionFactory
from backend.utils.suggestion_context import build_suggestion_context
from backend.agent.suggested_question_agent import SuggestedQuestionAgent
from backend.config.settings import settings
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
    ChatRunCancelResponse,
    ChatSessionCreate,
    ChatSessionOpenRequest,
    ChatSessionOpenResponse,
    ChatSessionResponse,
    ChatSuggestionsResponse,
)
from backend.services.exceptions import (
    ChatDivinationOwnershipError,
    ChatMessageNotFoundError,
    ChatRunAlreadyActiveError,
    ChatSessionArchivedError,
    ChatSessionNotFoundError,
    ChatSuggestionGenerationError,
    ChatSuggestionSourceError,
)
from backend.services.chat_run_registry import (
    ChatRunConflictError,
    ChatRunRegistry,
    chat_run_registry,
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
        suggestions_enabled: bool = True,
        memory_compactor: ChatMemoryCompactor | None = None,
        run_registry: ChatRunRegistry = chat_run_registry,
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
        self._suggestions_enabled = suggestions_enabled
        self._memory_compactor = memory_compactor
        self._run_registry = run_registry

    async def prepare_run(
        self,
        *,
        request_id: uuid.UUID,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """预登记本轮执行，让独立 HTTP 请求能够可靠停止 SSE 任务。"""
        try:
            await self._run_registry.prepare(
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
            )
        except ChatRunConflictError:
            raise ChatRunAlreadyActiveError(str(session_id)) from None

    async def cancel_run(
        self,
        *,
        request_id: uuid.UUID,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ChatRunCancelResponse:
        """显式停止当前会话的一轮 Agent 执行。"""
        await self._get_session_model(session_id, user_id)
        cancel_status = await self._run_registry.cancel(
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
        )
        messages = {
            "cancelled": "已停止本次回答。",
            "cancelling": "停止请求已发送，模型正在结束本次回答。",
            "already_finished": "本次回答已经结束，无需再次停止。",
        }
        return ChatRunCancelResponse(
            request_id=request_id,
            status=cancel_status,
            message=messages[cancel_status],
        )

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
        divination_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChatSessionResponse]:
        rows = await self._session_repository.list_for_user(
            user_id,
            status=status,
            divination_id=divination_id,
            limit=limit,
            offset=offset,
        )
        return [
            ChatSessionResponse.model_validate(row)
            for row in rows
        ]

    async def open_divination_session(
        self,
        payload: ChatSessionOpenRequest,
        user_id: uuid.UUID,
    ) -> ChatSessionOpenResponse:
        """复用指定卦例最近的会话，或按用户要求新建独立讨论。"""
        await self._ensure_divination_owned(payload.divination_id, user_id)
        related_count = await self._session_repository.count_for_divination(
            user_id,
            payload.divination_id,
        )

        if payload.mode == "reuse_latest" and related_count:
            chat_session = (
                await self._session_repository.get_latest_for_divination(
                    user_id,
                    payload.divination_id,
                )
            )
            if chat_session is not None:
                # “继续问易”代表明确的恢复意图，归档会话在这里自动恢复。
                if chat_session.status == "archived":
                    await self._session_repository.update(
                        chat_session,
                        {"status": "active"},
                    )
                    await self._session.commit()
                    await self._session.refresh(chat_session)
                return ChatSessionOpenResponse(
                    created=False,
                    related_session_count=related_count,
                    session=ChatSessionResponse.model_validate(chat_session),
                )

        chat_session = ChatSession(
            user_id=user_id,
            title=payload.title,
            active_divination_id=payload.divination_id,
        )
        await self._session_repository.add(chat_session)
        await self._session.commit()
        await self._session.refresh(chat_session)
        return ChatSessionOpenResponse(
            created=True,
            related_session_count=related_count + 1,
            session=ChatSessionResponse.model_validate(chat_session),
        )

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
        request_id: uuid.UUID | None = None,
        model: str | None = None,
    ) -> AsyncIterator[ChatEvent]:
        """持久化用户输入，执行 Agent，并逐事件保存可观察结果。"""
        request_id = request_id or uuid.uuid4()
        # Service 级测试和内部调用可以不经过 API 预登记；HTTP 路由则会在
        # 返回 StreamingResponse 前登记，以便停止请求尽早找到本轮任务。
        if not await self._run_registry.is_prepared(request_id):
            await self.prepare_run(
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
            )
        user_message_model: ChatMessage | None = None
        user_message_id: uuid.UUID | None = None
        sdk_session = None
        sdk_item_count_before_run: int | None = None
        visible_chunks: list[str] = []
        pending_tool_calls: dict[str, ChatEvent] = {}
        terminal_event_seen = False
        side_effect_completed = False
        try:
            chat_session = await self._get_session_model(session_id, user_id)
            if chat_session.status != "active":
                raise ChatSessionArchivedError(str(session_id))

            message_text = user_message.strip()
            user_message_model = await self._append_message(
                chat_session,
                user_id=user_id,
                role="user",
                content=message_text,
                payload={"client_request_id": str(request_id)},
                divination_id=chat_session.active_divination_id,
            )
            updates: dict[str, Any] = {"last_message_at": utc_now()}
            if chat_session.title is None:
                updates["title"] = message_text[:100]
            await self._session_repository.update(chat_session, updates)
            await self._session.commit()
            user_message_id = user_message_model.id

            await self._run_registry.activate(request_id)
            yield ChatEvent(
                event_type=ChatEventType.RUN_STARTED,
                request_id=request_id,
            )

            memory_summary = chat_session.summary
            if self._memory_compactor is not None:
                try:
                    compaction = await self._memory_compactor.compact_if_needed(
                        session_id=session_id,
                        user_id=user_id,
                    )
                    memory_summary = compaction.summary
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # 摘要是派生缓存；失败时保留 SDK Items 并继续主对话。
                    await self._session.rollback()
                    logger.exception(
                        "会话 %s 的长期记忆压缩失败，本轮使用未压缩上下文",
                        session_id,
                    )

            run_context = AgentRunContext(
                user_id=user_id,
                session_id=session_id,
                divination_service=self._divination_service,
                chat_divination_workflow=self._chat_divination_workflow,
                active_divination_id=chat_session.active_divination_id,
                workflow_state=chat_session.workflow_state,
            )
            sdk_session = self._agent_session_factory.create(
                session_id,
                memory_summary=memory_summary,
            )
            sdk_item_count_before_run = len(await sdk_session.get_items())

            # SDK 会在后台执行 Function Tool，并先发出 tool_call_started。
            # 工具与本 Service 共享请求级 AsyncSession，因此工具完成前不能在这里
            # flush；先缓存开始事件，收到结果后再按调用、结果顺序持久化。
            async for event in self._chatbot.stream(
                user_message=message_text,
                context=run_context,
                session=sdk_session,
                model=model or chat_session.model,
            ):
                outbound_event = event
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
                        event.event_type == ChatEventType.TOOL_CALL_COMPLETED
                        and event.tool_name
                        in {
                            "process_divination_request",
                            "request_initial_interpretation",
                            "cancel_divination_request",
                        }
                    ):
                        side_effect_completed = True
                    if (
                        event.tool_result is not None
                        and isinstance(event.tool_result.data, dict)
                    ):
                        candidate = event.tool_result.data.get(
                            "divination_id"
                        )
                        if isinstance(candidate, str):
                            run_context.active_divination_id = candidate
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
                    # 前端以已落库消息 ID 异步请求追问，不再阻塞主 SSE。
                    outbound_event = event.model_copy(
                        update={"message_id": completed_assistant.id}
                    )
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

                yield outbound_event
        except asyncio.CancelledError:
            await self._session.rollback()
            if sdk_session is not None and sdk_item_count_before_run is not None:
                await self._rollback_sdk_turn(
                    sdk_session,
                    sdk_item_count_before_run,
                )
            if not terminal_event_seen:
                chat_session = await self._get_session_model(
                    session_id,
                    user_id,
                )
                if user_message_id is not None:
                    persisted_user = await self._message_repository.get_for_user(
                        user_message_id,
                        user_id,
                    )
                    if persisted_user is not None:
                        await self._message_repository.update(
                            persisted_user,
                            {"status": "cancelled"},
                        )
                await self._persist_failed_assistant(
                    chat_session,
                    user_id,
                    (
                        "已停止本次回答，已经完成的排盘操作已保留。"
                        if side_effect_completed
                        else "已停止本次回答。"
                    ),
                    status="cancelled",
                )
            raise
        except Exception:
            await self._session.rollback()
            logger.exception("Chatbot 流式执行或消息持久化失败")
            raise
        finally:
            await self._run_registry.finish(request_id)

    @staticmethod
    async def _rollback_sdk_turn(
        sdk_session: Any,
        baseline_count: int,
    ) -> None:
        """撤销本轮新增的 SDK Items，同时保留取消前的会话上下文。"""
        try:
            current_count = len(await sdk_session.get_items())
            while current_count > baseline_count:
                popped = await sdk_session.pop_item()
                if popped is None:
                    break
                current_count -= 1
        except Exception:
            logger.exception("取消 Chat Run 时回滚本轮 SDK Items 失败")

    async def generate_suggestions(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
    ) -> ChatSuggestionsResponse:
        """为一条已完成回答生成追问；结果按来源消息一对一缓存。"""
        chat_session = await self._get_session_model(session_id, user_id)
        assistant_message = await self._message_repository.get_for_user(
            assistant_message_id,
            user_id,
        )
        if (
            assistant_message is None
            or assistant_message.session_id != session_id
        ):
            raise ChatMessageNotFoundError(str(assistant_message_id))
        if (
            assistant_message.role != "assistant"
            or assistant_message.message_type != "text"
            or assistant_message.status != "completed"
            or not assistant_message.content
        ):
            raise ChatSuggestionSourceError(str(assistant_message_id))

        # 用户关闭追问建议后，不返回历史缓存，也绝不触发新的模型调用。
        if not self._suggestions_enabled:
            return ChatSuggestionsResponse(
                source_message_id=assistant_message_id,
                questions=[],
                cached=False,
            )

        cached = await self._message_repository.get_suggestions_for_source(
            assistant_message_id,
            user_id,
        )
        if cached is not None:
            payload = SuggestedQuestionsPayload.model_validate(cached.payload)
            return ChatSuggestionsResponse(
                source_message_id=assistant_message_id,
                questions=payload.questions,
                cached=True,
            )

        # 没有关联卦例时不调用模型，避免普通寒暄和信息收集阶段浪费 Token。
        if assistant_message.divination_id is None:
            return ChatSuggestionsResponse(
                source_message_id=assistant_message_id,
                questions=[],
                cached=False,
            )
        if self._suggested_question_agent is None:
            raise ChatSuggestionGenerationError("追问 Agent 未配置")

        user_message = await self._message_repository.get_latest_user_before(
            session_id=session_id,
            user_id=user_id,
            before_sequence=assistant_message.sequence,
        )
        compact_user, compact_answer = build_suggestion_context(
            user_message=user_message.content if user_message else "",
            assistant_answer=assistant_message.content,
            answer_max_chars=settings.suggestion_context_max_chars,
            user_max_chars=settings.suggestion_user_message_max_chars,
        )
        # LLM 调用期间不需要持有查询事务；同时保存所有后续操作所需纯值，
        # 避免 rollback 后访问过期 ORM 属性。
        divination_id = assistant_message.divination_id
        await self._session.commit()
        try:
            generated = await self._suggested_question_agent.generate(
                user_message=compact_user,
                assistant_answer=compact_answer,
            )
            payload = SuggestedQuestionsPayload(
                source_message_id=assistant_message_id,
                questions=generated.questions,
            )
            await self._append_message(
                chat_session,
                user_id,
                role="assistant",
                message_type="suggestions",
                payload=payload.model_dump(mode="json"),
                source_message_id=assistant_message_id,
                divination_id=divination_id,
            )
            await self._session.commit()
            return ChatSuggestionsResponse(
                source_message_id=assistant_message_id,
                questions=generated.questions,
                cached=False,
            )
        except IntegrityError:
            # 两个回调并发时唯一约束只允许一个成功，失败方读取胜出结果。
            await self._session.rollback()
            cached = (
                await self._message_repository.get_suggestions_for_source(
                    assistant_message_id,
                    user_id,
                )
            )
            if cached is not None:
                payload = SuggestedQuestionsPayload.model_validate(
                    cached.payload
                )
                return ChatSuggestionsResponse(
                    source_message_id=assistant_message_id,
                    questions=payload.questions,
                    cached=True,
                )
            logger.exception(
                "会话 %s 的追问建议违反数据库约束",
                session_id,
            )
            raise ChatSuggestionGenerationError(
                "追问建议保存失败"
            ) from None
        except Exception:
            await self._session.rollback()
            logger.exception(
                "会话 %s 的追问建议生成或保存失败",
                session_id,
            )
            raise ChatSuggestionGenerationError(
                "追问建议生成失败"
            ) from None

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
        source_message_id: uuid.UUID | None = None,
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
            source_message_id=source_message_id,
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
