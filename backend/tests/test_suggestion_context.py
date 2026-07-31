"""追问上下文裁剪测试。"""
from backend.utils.suggestion_context import (
    DISCLAIMER,
    build_suggestion_context,
)


def test_short_suggestion_context_only_removes_disclaimer():
    user, answer = build_suggestion_context(
        user_message="  这件事的应期怎么看？  ",
        assistant_answer=(
            "## 判断\n\n先看用神，再看动爻。\n\n"
            f"> {DISCLAIMER}。"
        ),
        answer_max_chars=200,
        user_max_chars=50,
    )

    assert user == "这件事的应期怎么看？"
    assert answer == "## 判断\n\n先看用神，再看动爻。"
    assert DISCLAIMER not in answer


def test_long_suggestion_context_keeps_opening_and_meaningful_tail():
    user, answer = build_suggestion_context(
        user_message="问" * 50,
        assistant_answer=(
            "## 卦象主题\n\n"
            + "中段分析。" * 40
            + "\n\n## 应期\n\n末尾有效判断。"
            + f"\n\n> {DISCLAIMER}"
        ),
        answer_max_chars=120,
        user_max_chars=20,
    )

    assert user == "问" * 20
    assert len(answer) <= 120
    assert answer.startswith("## 卦象主题")
    assert "末尾有效判断" in answer
    assert DISCLAIMER not in answer
