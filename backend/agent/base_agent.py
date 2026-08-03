"""无工具角色 Agent 的共同运行封装。"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator

from agents import Agent, RawResponsesStreamEvent, Runner
from openai.types.responses import ResponseTextDeltaEvent

from backend.agent.runtime.model import AgentModelFactory
from backend.services.llm_usage import LLMUsageRecorder


class BaseAgent:
    """保留易读继承风格，模型客户端统一由 AgentModelFactory 创建。"""

    def __init__(
        self,
        name: str,
        instructions: str,
        *,
        model_factory: AgentModelFactory | None = None,
        usage_recorder: LLMUsageRecorder | None = None,
        agent_role: str | None = None,
    ):
        self.name = name
        self._model_factory = model_factory or AgentModelFactory()
        self._model_name = self._model_factory.default_model
        self._usage_recorder = usage_recorder
        self._agent_role = agent_role or name
        self.agent = Agent(
            name=name,
            model=self._model_factory.create(),
            instructions=instructions,
        )

    async def chat(self, user_input: str) -> str:
        started = time.perf_counter()
        try:
            result = await Runner.run(self.agent, user_input)
        except Exception:
            await self._record(started, status="failed", error_code="model_error")
            raise
        await self._record(
            started,
            status="completed",
            usage=result.context_wrapper.usage,
        )
        return str(result.final_output or "")

    async def chat_stream(self, user_input: str) -> AsyncIterator[str]:
        started = time.perf_counter()
        result = Runner.run_streamed(self.agent, user_input)
        try:
            async for event in result.stream_events():
                if (
                    isinstance(event, RawResponsesStreamEvent)
                    and isinstance(event.data, ResponseTextDeltaEvent)
                    and event.data.delta
                ):
                    yield event.data.delta
        except Exception:
            await self._record(started, status="failed", error_code="model_error")
            raise
        await self._record(
            started,
            status="completed",
            usage=result.context_wrapper.usage,
        )

    async def _record(
        self,
        started: float,
        *,
        status: str,
        usage=None,
        error_code: str | None = None,
    ) -> None:
        if self._usage_recorder is None:
            return
        await self._usage_recorder.record(
            agent_role=self._agent_role,
            model=self._model_name,
            base_url=self._model_factory.base_url,
            duration_ms=int((time.perf_counter() - started) * 1000),
            status=status,
            usage=usage,
            error_code=error_code,
        )
