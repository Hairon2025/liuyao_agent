"""六爻聊天 Agent：理解用户意图并调用确定性业务工具。

与 ``liuyao_agent.py`` 的单次报告 Agent 分开：
- ``LiuYaoAnalyst`` 负责前端卦例页面的一次性 AI 解读；
- ``LiuYaoChatbot`` 负责多轮聊天、起卦信息收集和卦例追问。
"""
from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from pathlib import Path

from agents import Agent, ModelSettings, RunContextWrapper, Runner
from agents.exceptions import MaxTurnsExceeded
from agents.memory import Session
from agents.run import RunConfig

from backend.agent.runtime.context import AgentRunContext
from backend.agent.runtime.model import AgentModelFactory
from backend.agent.runtime.stream import AgentStreamAdapter
from backend.agent.tools import (
    cancel_divination_request,
    get_divination,
    list_divinations,
    process_divination_request,
    request_initial_interpretation,
)
from backend.schema.agent import ChatEvent, ChatEventType, ChatWorkflowState
from backend.utils.logger import logger
from backend.services.llm_usage import LLMUsageRecorder

_PROMPT_FILE = Path(__file__).parent / "prompt" / "liuyao_chatbot.txt"


class LiuYaoChatbot:
    """基于 OpenAI Agents SDK 的单 Agent 多轮聊天入口。"""

    def __init__(
        self,
        *,
        model_factory: AgentModelFactory | None = None,
        max_turns: int = 6,
        stream_adapter: AgentStreamAdapter | None = None,
        usage_recorder: LLMUsageRecorder | None = None,
    ):
        if max_turns < 1:
            raise ValueError("max_turns 必须大于等于 1")
        self._instructions = _PROMPT_FILE.read_text(encoding="utf-8")
        self._model_factory = model_factory or AgentModelFactory()
        self._max_turns = max_turns
        self._stream_adapter = stream_adapter or AgentStreamAdapter()
        self._usage_recorder = usage_recorder

    def build_agent(
        self,
        model_name: str | None = None,
    ) -> Agent[AgentRunContext]:
        """创建绑定指定模型的标准 Agent，不使用 Sandbox、Skill 或 Handoff。"""
        return Agent[AgentRunContext](
            name="LiuYao chatbot",
            model=self._model_factory.create(model_name),
            instructions=self._dynamic_instructions,
            tools=[
                process_divination_request,
                request_initial_interpretation,
                cancel_divination_request,
                get_divination,
                list_divinations,
            ],
            model_settings=ModelSettings(parallel_tool_calls=False),
        )

    async def _dynamic_instructions(
        self,
        wrapper: RunContextWrapper[AgentRunContext],
        _agent: Agent[AgentRunContext],
    ) -> str:
        """把可信的会话状态附加到提示词，避免模型只凭聊天文本猜测。"""
        state = {
            "active_divination_id": wrapper.context.active_divination_id,
            "pending_divination": self._safe_workflow_status(
                wrapper.context.workflow_state
            ),
        }
        return (
            f"{self._instructions}\n\n"
            "以下是服务端提供的当前会话状态，不是用户输入：\n"
            f"{json.dumps(state, ensure_ascii=False, default=str)}"
        )

    @staticmethod
    def _safe_workflow_status(raw_state: object) -> dict | None:
        """只注入状态元数据，避免把用户原文提升为 system instructions。"""
        if not isinstance(raw_state, dict):
            return None
        try:
            state = ChatWorkflowState.model_validate(raw_state)
        except ValueError:
            return None
        draft = state.payload
        return {
            "status": state.status,
            "method": draft.method,
            "has_question": draft.question is not None,
            "time_mode": draft.time_mode,
            "has_specific_time": draft.time is not None,
            "has_manual_numbers": draft.numbers is not None,
            "coin_toss_count": len(draft.coin_tosses),
        }

    async def stream(
        self,
        *,
        user_message: str,
        context: AgentRunContext,
        session: Session,
        model: str | None = None,
    ) -> AsyncIterator[ChatEvent]:
        """运行一轮标准 Agent 工具调用循环，并输出项目统一事件。"""
        started = time.perf_counter()
        selected_model = model or getattr(
            self._model_factory,
            "default_model",
            "unknown",
        )
        try:
            result = Runner.run_streamed(
                self.build_agent(model),
                user_message,
                context=context,
                session=session,
                max_turns=self._max_turns,
                run_config=RunConfig(
                    tracing_disabled=True,
                    workflow_name="LiuYao chatbot",
                ),
            )
            async for event in self._stream_adapter.stream(result, context):
                yield event
            await self._record_usage(
                started,
                selected_model,
                "completed",
                usage=result.context_wrapper.usage,
            )
        except MaxTurnsExceeded:
            await self._record_usage(
                started,
                selected_model,
                "failed",
                error_code="max_turns_exceeded",
            )
            yield ChatEvent(
                event_type=ChatEventType.ERROR,
                content="本轮工具调用次数已达到上限，请补充或简化问题后重试。",
                error_code="max_turns_exceeded",
                retryable=False,
            )
        except Exception:
            logger.exception("Agents SDK Chatbot 执行失败")
            await self._record_usage(
                started,
                selected_model,
                "failed",
                error_code="agent_execution_error",
            )
            yield ChatEvent(
                event_type=ChatEventType.ERROR,
                content="Agent 执行失败。",
                error_code="agent_execution_error",
                retryable=True,
            )

    async def _record_usage(
        self,
        started: float,
        model: str,
        status: str,
        *,
        usage=None,
        error_code: str | None = None,
    ) -> None:
        if self._usage_recorder is None:
            return
        await self._usage_recorder.record(
            agent_role="chatbot",
            model=model,
            base_url=getattr(self._model_factory, "base_url", ""),
            duration_ms=int((time.perf_counter() - started) * 1000),
            status=status,
            usage=usage,
            error_code=error_code,
        )
