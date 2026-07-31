"""聊天多 Agent 的应用层编排。

执行顺序由 Python 固定控制：
1. ChatCoordinatorAgent 理解意图并调用业务工具；
2. 新卦创建或已有排盘明确请求首次解读后，LiuYaoAnalyst 生成并保存报告；
3. 追问建议由 ChatService 在正文落库后调用独立 Agent 生成。
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from agents.memory import Session

from backend.agent.chatbot_agent import LiuYaoChatbot
from backend.agent.liuyao_agent import LiuYaoAnalyst
from backend.agent.runtime.context import AgentRunContext
from backend.schema.agent import ChatEvent, ChatEventType
from backend.services.divination import DivinationService
from backend.services.exceptions import MarkdownNotFoundError
from backend.utils.logger import logger


class ChatAgentOrchestrator:
    """串行协调聊天 Agent 与首次报告 Agent。"""

    def __init__(
        self,
        *,
        coordinator: LiuYaoChatbot,
        analyst: LiuYaoAnalyst,
        divination_service: DivinationService,
    ):
        self._coordinator = coordinator
        self._analyst = analyst
        self._divination_service = divination_service

    async def stream(
        self,
        *,
        user_message: str,
        context: AgentRunContext,
        session: Session,
        model: str | None = None,
    ) -> AsyncIterator[ChatEvent]:
        """运行协调 Agent；需要首次正式解读时切换到 LiuYaoAnalyst。"""
        interpretation_divination_id: str | None = None

        async for event in self._coordinator.stream(
            user_message=user_message,
            context=context,
            session=session,
            model=model,
        ):
            candidate = self._interpretation_divination_id(event)
            if candidate is not None:
                interpretation_divination_id = candidate

            # 首次完整回答统一交给 LiuYaoAnalyst。协调 Agent 在触发工具
            # 完成后的说明不展示，避免同一卦象被两个 Agent 重复解读。
            if (
                interpretation_divination_id is not None
                and event.event_type in {
                    ChatEventType.TEXT_DELTA,
                    ChatEventType.MESSAGE_COMPLETED,
                    ChatEventType.ERROR,
                }
            ):
                continue
            yield event

        if interpretation_divination_id is None:
            return

        try:
            markdown = await self._get_or_generate_markdown(
                interpretation_divination_id,
                context,
            )
            chunks: list[str] = []
            async for chunk in self._analyst.interpret_stream(markdown):
                if not chunk:
                    continue
                chunks.append(chunk)
                yield ChatEvent(
                    event_type=ChatEventType.TEXT_DELTA,
                    content=chunk,
                )

            report = "".join(chunks).strip()
            if not report:
                raise RuntimeError("LiuYaoAnalyst 返回了空报告")

            # canonical copy：供卦例页和未来追问读取。
            await self._divination_service.save_interpretation(
                interpretation_divination_id,
                context.user_id,
                report,
            )
            # SDK Session 还需看到用户实际收到的报告，而不是被隐藏的协调
            # Agent 收尾文本，保证下一轮能自然追问。
            await session.add_items(
                [{"role": "assistant", "content": report}]
            )
            yield ChatEvent(
                event_type=ChatEventType.MESSAGE_COMPLETED,
                content=report,
            )
        except Exception:
            logger.exception(
                "卦例 %s 首次 AI 解读生成或保存失败",
                interpretation_divination_id,
            )
            yield ChatEvent(
                event_type=ChatEventType.ERROR,
                content=(
                    "排盘已经保存，但首次 AI 解读生成失败。"
                    "你可以在卦例详情页重新生成。"
                ),
                error_code="initial_interpretation_error",
                retryable=True,
            )

    async def _get_or_generate_markdown(
        self,
        divination_id: str,
        context: AgentRunContext,
    ) -> str:
        try:
            return await self._divination_service.get_markdown(
                divination_id,
                context.user_id,
            )
        except MarkdownNotFoundError:
            return await self._divination_service.generate_markdown(
                divination_id,
                context.user_id,
            )

    @staticmethod
    def _interpretation_divination_id(event: ChatEvent) -> str | None:
        if (
            event.event_type != ChatEventType.TOOL_CALL_COMPLETED
            or event.tool_result is None
            or not isinstance(event.tool_result.data, dict)
        ):
            return None
        status = event.tool_result.data.get("status")
        if (
            event.tool_name == "process_divination_request"
            and status == "created"
        ):
            pass
        elif (
            event.tool_name == "request_initial_interpretation"
            and status == "ready_for_interpretation"
        ):
            pass
        else:
            return None
        candidate = event.tool_result.data.get("divination_id")
        return candidate if isinstance(candidate, str) else None
