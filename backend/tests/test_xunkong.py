"""core/xunkong.py 单元测试

覆盖 6 旬的首日 / 末日 / 中段，防止 60-cycle 索引算错的回归
（例如：戊寅日之前被错误归入甲子旬 → 戌亥，正确应为甲戌旬 → 申酉）。
"""
from __future__ import annotations

import pytest

from backend.core.xunkong import get_xunkong


# 6 旬 × {首日, 末日} + 关键回归 case (戊寅)
@pytest.mark.parametrize(
    "day_ganzhi,expected_kong",
    [
        # 甲子旬
        ("甲子", ["戌", "亥"]),
        ("乙丑", ["戌", "亥"]),
        ("丙寅", ["戌", "亥"]),
        ("丁卯", ["戌", "亥"]),
        ("戊辰", ["戌", "亥"]),
        ("己巳", ["戌", "亥"]),
        ("庚午", ["戌", "亥"]),
        ("辛未", ["戌", "亥"]),
        ("壬申", ["戌", "亥"]),
        ("癸酉", ["戌", "亥"]),
        # 甲戌旬（包含关键的 戊寅 回归 case）
        ("甲戌", ["申", "酉"]),
        ("乙亥", ["申", "酉"]),
        ("丙子", ["申", "酉"]),
        ("丁丑", ["申", "酉"]),
        ("戊寅", ["申", "酉"]),  # ← 之前 bug 案例
        ("己卯", ["申", "酉"]),
        ("庚辰", ["申", "酉"]),
        ("辛巳", ["申", "酉"]),
        ("壬午", ["申", "酉"]),
        ("癸未", ["申", "酉"]),
        # 甲申旬
        ("甲申", ["午", "未"]),
        ("癸巳", ["午", "未"]),
        # 甲午旬
        ("甲午", ["辰", "巳"]),
        ("癸卯", ["辰", "巳"]),
        # 甲辰旬
        ("甲辰", ["寅", "卯"]),
        ("癸丑", ["寅", "卯"]),
        # 甲寅旬（最末旬，跨年循环）
        ("甲寅", ["子", "丑"]),
        ("癸亥", ["子", "丑"]),
    ],
)
def test_xunkong_all_60_day_combinations(day_ganzhi, expected_kong):
    """6 旬全覆盖：每个旬的首日 + 末日 + 至少 1 个中段日。"""
    assert get_xunkong(day_ganzhi) == expected_kong


def test_xunkong_returns_two_items():
    """60-cycle 内的所有合法日干支都返回恰好 2 个地支。

    注：不是所有 10 天干 × 12 地支 = 120 组合都合法（60-cycle 中只 60 个）。
    非法组合（如 甲丑）不在测试范围内——函数会抛 ValueError。
    """
    from backend.core.constants import GAN_ORDER, ZHI_ORDER

    for i in range(60):
        gan = GAN_ORDER[i % 10]
        zhi = ZHI_ORDER[i % 12]
        result = get_xunkong(gan + zhi)
        assert len(result) == 2
        assert all(z in ZHI_ORDER for z in result)


def test_xunkong_returns_empty_for_too_short_input():
    """输入太短（< 2 字符）返回空 list 而非抛异常。"""
    assert get_xunkong("") == ["", ""]
    assert get_xunkong("甲") == ["", ""]


def test_xunkong_60_cycle_continuity():
    """相邻 60-cycle 日的 旬空 切换点：甲子旬末日（癸酉）→ 甲戌旬首日（甲戌）。"""
    assert get_xunkong("癸酉") == ["戌", "亥"]  # 甲子旬末日
    assert get_xunkong("甲戌") == ["申", "酉"]  # 甲戌旬首日
    assert get_xunkong("癸亥") == ["子", "丑"]  # 甲寅旬末日
    assert get_xunkong("甲子") == ["戌", "亥"]  # 60-cycle 回到起点