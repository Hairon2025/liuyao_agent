"""长期记忆摘要 Agent 的结构化输出测试。"""
from __future__ import annotations

import pytest

from backend.agent.memory_summary_agent import MemorySummaryAgent


def test_memory_summary_agent_parses_plain_and_fenced_json():
    raw = (
        '{"current_focus":"继续分析工作卦",'
        '"user_context":["用户关注未来三个月"],'
        '"user_preferences":["希望重点分析应期"],'
        '"divination_context":["卦例 abc"],'
        '"key_conclusions":["后期存在变化"],'
        '"unresolved_questions":["具体应期尚未确认"]}'
    )

    plain = MemorySummaryAgent.parse_output(raw)
    fenced = MemorySummaryAgent.parse_output(f"```json\n{raw}\n```")

    assert plain.current_focus == "继续分析工作卦"
    assert fenced.unresolved_questions == ["具体应期尚未确认"]


@pytest.mark.parametrize(
    "raw_output",
    [
        "不是 JSON",
        '{"current_focus":"测试","unknown":[]}',
        '{"current_focus":null,"user_context":["x"],'
        '"user_preferences":[],"divination_context":[],'
        '"key_conclusions":[],"unresolved_questions":[],"extra":1}',
    ],
)
def test_memory_summary_agent_rejects_invalid_output(raw_output):
    with pytest.raises(ValueError):
        MemorySummaryAgent.parse_output(raw_output)
