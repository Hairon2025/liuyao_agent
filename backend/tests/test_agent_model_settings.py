"""各角色 Agent 的思考模式配置测试。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.agent.liuyao_agent import LiuYaoAnalyst
from backend.agent.memory_summary_agent import MemorySummaryAgent
from backend.agent.runtime.model import AgentModelFactory
from backend.agent.suggested_question_agent import SuggestedQuestionAgent


def _factory() -> AgentModelFactory:
    return AgentModelFactory(
        api_key="test-key",
        base_url="https://llm.example.com/v1",
        default_model="test-model",
    )


def _assert_thinking_disabled(agent) -> None:
    model_settings = agent.model_settings
    assert model_settings is not None
    assert model_settings.reasoning is not None
    assert model_settings.reasoning.effort == "none"
    assert model_settings.extra_body == {
        "thinking": {"type": "disabled"}
    }


def test_analyst_disables_thinking_mode():
    analyst = LiuYaoAnalyst(model_factory=_factory())
    _assert_thinking_disabled(analyst.agent)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module_path", "agent_factory"),
    [
        (
            "backend.agent.suggested_question_agent.Runner.run",
            lambda: SuggestedQuestionAgent(model_factory=_factory()),
        ),
        (
            "backend.agent.memory_summary_agent.Runner.run",
            lambda: MemorySummaryAgent(model_factory=_factory()),
        ),
    ],
)
async def test_auxiliary_agents_disable_thinking_mode(
    monkeypatch,
    module_path,
    agent_factory,
):
    captured = {}

    async def fake_run(agent, *_args, **_kwargs):
        captured["agent"] = agent
        return SimpleNamespace(
            final_output="{}",
            context_wrapper=SimpleNamespace(usage=None),
        )

    monkeypatch.setattr(module_path, fake_run)
    auxiliary_agent = agent_factory()
    await auxiliary_agent._run("test")

    _assert_thinking_disabled(captured["agent"])
