"""把旧记忆与新增 Session Items 合并为结构化长期记忆。"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from agents import Agent, Runner
from agents.run import RunConfig

from backend.agent.runtime.model import AgentModelFactory
from backend.schema.agent.memory import ConversationMemory
from backend.services.llm_usage import LLMUsageRecorder

_PROMPT_FILE = Path(__file__).parent / "prompt" / "memory_summary.txt"
_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class MemorySummaryAgent:
    """独立、可配置模型的长期记忆摘要 Agent。"""

    def __init__(
        self,
        *,
        model_factory: AgentModelFactory | None = None,
        usage_recorder: LLMUsageRecorder | None = None,
    ):
        self._model_factory = model_factory or AgentModelFactory()
        self._agent: Agent | None = None
        self._usage_recorder = usage_recorder

    async def summarize(
        self,
        *,
        previous_memory: str | None,
        conversation_items: list[str],
    ) -> ConversationMemory:
        prompt = self._build_input(previous_memory, conversation_items)
        raw_output = await self._run(prompt)
        try:
            return self.parse_output(raw_output)
        except ValueError as exc:
            repaired = await self._run(
                f"{prompt}\n\n"
                f"你上一次的输出未通过校验：{exc}。"
                "请只重新输出符合要求的 JSON，不要解释。"
            )
            return self.parse_output(repaired)

    async def _run(self, prompt: str) -> str:
        if self._agent is None:
            self._agent = Agent(
                name="memory_summary_agent",
                model=self._model_factory.create(),
                instructions=_PROMPT_FILE.read_text(encoding="utf-8"),
            )
        started = time.perf_counter()
        try:
            result = await Runner.run(
                self._agent,
                prompt,
                max_turns=1,
                run_config=RunConfig(
                    tracing_disabled=True,
                    workflow_name="LiuYao memory summary",
                ),
            )
        except Exception:
            await self._record(started, "failed", error_code="model_error")
            raise
        await self._record(
            started,
            "completed",
            usage=result.context_wrapper.usage,
        )
        return str(result.final_output or "")

    async def _record(
        self,
        started: float,
        status: str,
        *,
        usage=None,
        error_code: str | None = None,
    ) -> None:
        if self._usage_recorder is None:
            return
        await self._usage_recorder.record(
            agent_role="memory",
            model=self._model_factory.default_model,
            base_url=self._model_factory.base_url,
            duration_ms=int((time.perf_counter() - started) * 1000),
            status=status,
            usage=usage,
            error_code=error_code,
        )

    @staticmethod
    def _build_input(
        previous_memory: str | None,
        conversation_items: list[str],
    ) -> str:
        payload = {
            "previous_memory": previous_memory,
            "new_conversation_items": conversation_items,
        }
        return (
            "请更新下面的长期记忆：\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

    @staticmethod
    def parse_output(raw_output: str) -> ConversationMemory:
        normalized = raw_output.strip()
        match = _JSON_BLOCK.fullmatch(normalized)
        if match is not None:
            normalized = match.group(1)
        try:
            return ConversationMemory.model_validate_json(normalized)
        except ValueError as exc:
            raise ValueError("长期记忆不是合法的结构化 JSON") from exc
