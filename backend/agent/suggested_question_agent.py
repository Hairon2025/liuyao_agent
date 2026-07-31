"""根据最新一轮问答生成结构化追问建议。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from agents import Agent, Runner
from agents.run import RunConfig

from backend.agent.runtime.model import AgentModelFactory
from backend.schema.agent.suggestion import SuggestedQuestions

_PROMPT_FILE = Path(__file__).parent / "prompt" / "suggested_questions.txt"
_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class SuggestedQuestionAgent:
    """只负责追问建议，不参与起卦、排盘或正式解读。"""

    def __init__(
        self,
        *,
        model_factory: AgentModelFactory | None = None,
    ):
        # 延迟创建 OpenAI client，使无 API Key 的纯单元测试仍可导入应用。
        self._model_factory = model_factory or AgentModelFactory()
        self._agent: Agent | None = None

    async def generate(
        self,
        *,
        user_message: str,
        assistant_answer: str,
    ) -> SuggestedQuestions:
        """生成并校验 JSON；格式错误时给模型一次自我修复机会。"""
        prompt = self._build_input(user_message, assistant_answer)
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
        """追问 Agent 无工具，一次运行只允许一个模型回合。"""
        if self._agent is None:
            self._agent = Agent(
                name="suggested_question_agent",
                model=self._model_factory.create(),
                instructions=_PROMPT_FILE.read_text(encoding="utf-8"),
            )
        result = await Runner.run(
            self._agent,
            prompt,
            max_turns=1,
            run_config=RunConfig(
                tracing_disabled=True,
                workflow_name="LiuYao suggested questions",
            ),
        )
        return str(result.final_output or "")

    @staticmethod
    def _build_input(user_message: str, assistant_answer: str) -> str:
        payload = {
            "latest_user_message": user_message,
            "latest_assistant_answer": assistant_answer,
        }
        return (
            "请根据下面这一轮对话生成追问建议：\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

    @staticmethod
    def parse_output(raw_output: str) -> SuggestedQuestions:
        """兼容纯 JSON 和常见的 Markdown JSON 代码块。"""
        normalized = raw_output.strip()
        match = _JSON_BLOCK.fullmatch(normalized)
        if match is not None:
            normalized = match.group(1)
        try:
            return SuggestedQuestions.model_validate_json(normalized)
        except ValueError as exc:
            raise ValueError("追问建议不是合法的结构化 JSON") from exc
