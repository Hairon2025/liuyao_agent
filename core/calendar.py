"""地支计算（移植自参考项目 dizhi.py）

根据公历年月日时计算对应的地支（子丑寅卯辰巳午未申酉戌亥）。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Final

EARTHLY_BRANCHES: Final[list[str]] = [
    "子", "丑", "寅", "卯", "辰", "巳",
    "午", "未", "申", "酉", "戌", "亥",
]

# 节气分界表（简化近似，与原参考项目一致）
# (month, day) → 对应农历月份起始节气
SOLAR_TERMS: Final[list[tuple[int, int]]] = [
    (2, 4),   # 寅月（正月）：立春
    (3, 6),   # 卯月（二月）：惊蛰
    (4, 5),   # 辰月（三月）：清明
    (5, 6),   # 巳月（四月）：立夏
    (6, 6),   # 午月（五月）：芒种
    (7, 7),   # 未月（六月）：小暑
    (8, 8),   # 申月（七月）：立秋
    (9, 8),   # 酉月（八月）：白露
    (10, 8),  # 戌月（九月）：寒露
    (11, 7),  # 亥月（十月）：立冬
    (12, 7),  # 子月（十一月）：大雪
    (1, 6),   # 丑月（十二月）：小寒
]


def get_year_branch(year: int) -> str:
    """计算年份地支（以 1900 年庚子年为基准）。"""
    offset = (year - 1900) % 12
    return EARTHLY_BRANCHES[offset]


def get_month_branch(year: int, month: int, day: int) -> str:
    """计算月份地支（按节气分界）。"""
    if month == 1:
        term_day = SOLAR_TERMS[11][1]
        return EARTHLY_BRANCHES[11] if day >= term_day else EARTHLY_BRANCHES[10]

    term_idx = month - 1
    prev_term_day = SOLAR_TERMS[term_idx - 1][1]
    if day >= prev_term_day:
        return EARTHLY_BRANCHES[term_idx - 1]
    return EARTHLY_BRANCHES[term_idx - 2]


def get_day_branch(year: int, month: int, day: int) -> str:
    """计算日地支（以 1900-01-01 庚子日为基准）。"""
    base_date = date(1900, 1, 1)
    target_date = date(year, month, day)
    offset = (target_date - base_date).days % 12
    return EARTHLY_BRANCHES[offset]


def get_hour_branch(hour: int) -> str:
    """计算时辰地支（每 2 小时为一个时辰）。"""
    # 23-1点 → 子时(0), 1-3点 → 丑时(1), ..., 21-23点 → 亥时(11)
    hour_segment = (hour + 1) // 2
    return EARTHLY_BRANCHES[hour_segment % 12]


def get_ganzhi(dt: datetime) -> dict[str, str]:
    """一次性返回年月日时四柱地支（暂不含天干）。"""
    return {
        "year": get_year_branch(dt.year),
        "month": get_month_branch(dt.year, dt.month, dt.day),
        "day": get_day_branch(dt.year, dt.month, dt.day),
        "hour": get_hour_branch(dt.hour),
    }
