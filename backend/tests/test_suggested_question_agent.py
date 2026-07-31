"""追问建议 Agent 的结构化输出测试。"""
from __future__ import annotations

import pytest

from backend.agent.suggested_question_agent import SuggestedQuestionAgent


def test_suggested_question_agent_parses_plain_and_fenced_json():
    plain = SuggestedQuestionAgent.parse_output(
        '{"questions":["用神为何取这一爻？","动爻如何影响结果？",'
        '"应期可以怎么看？"]}'
    )
    fenced = SuggestedQuestionAgent.parse_output(
        '```json\n{"questions":[]}\n```'
    )

    assert len(plain.questions) == 3
    assert fenced.questions == []


@pytest.mark.parametrize(
    "raw_output",
    [
        '{"questions":["只有一条"]}',
        '{"questions":["重复","重复","第三条"]}',
        "这不是 JSON",
    ],
)
def test_suggested_question_agent_rejects_invalid_output(raw_output):
    with pytest.raises(ValueError):
        SuggestedQuestionAgent.parse_output(raw_output)

