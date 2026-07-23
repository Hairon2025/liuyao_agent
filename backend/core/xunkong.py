"""旬空计算（移植自参考项目 main.py）

日干支由调用方通过 `core.calendar.get_ganzhi()` 提供（使用 lunar_python 保证节气精度）。
本模块仅负责：已知日干支 → 旬空地支。

旬空速查表：
    甲子旬（甲子 ~ 癸酉）：旬空 戌亥
    甲戌旬（甲戌 ~ 癸未）：旬空 申酉
    甲申旬（甲申 ~ 癸巳）：旬空 午未
    甲午旬（甲午 ~ 癸卯）：旬空 辰巳
    甲辰旬（甲辰 ~ 癸丑）：旬空 寅卯
    甲寅旬（甲寅 ~ 癸亥）：旬空 子丑
"""
from __future__ import annotations

from backend.core.constants import GAN_ORDER, ZHI_ORDER

# 六旬起点（按 60 甲子顺序）
XUN_START = ["甲子", "甲戌", "甲申", "甲午", "甲辰", "甲寅"]

# 旬 → 旬空地支
XUN_KONG = {
    "甲子": ["戌", "亥"],
    "甲戌": ["申", "酉"],
    "甲申": ["午", "未"],
    "甲午": ["辰", "巳"],
    "甲辰": ["寅", "卯"],
    "甲寅": ["子", "丑"],
}


def _ganzhi_to_60cycle_index(gan: str, zhi: str) -> int:
    """计算日干支在 60 甲子循环中的 0-based 索引（0=甲子, 59=癸亥）。

    60 甲子循环定义为：位置 i 对应 (gan_idx=i % 10, zhi_idx=i % 12)。
    给定 (gan, zhi) 需要求 i 满足两个同余式（CRT）。

    实现：枚举 0..59，规模固定且小（O(60)），无副作用，比直接套 CRT 公式可读。
    """
    gan_idx = GAN_ORDER.index(gan)
    zhi_idx = ZHI_ORDER.index(zhi)
    for i in range(60):
        if i % 10 == gan_idx and i % 12 == zhi_idx:
            return i
    raise ValueError(f"无效干支：{gan}{zhi}")


def get_xunkong(day_ganzhi: str) -> list[str]:
    """根据日干支计算旬空。

    Args:
        day_ganzhi: 日干支，如 "甲子"、"戊寅"（前两位字符必须是合法干支）

    Returns:
        旬空地支列表（按 60 甲子顺序的两个地支），如 ["申", "酉"]
    """
    if len(day_ganzhi) < 2:
        return ["", ""]

    gan = day_ganzhi[0]
    zhi = day_ganzhi[1]

    # 60-cycle 索引 → 旬索引（每 10 天一旬）→ 旬空
    cycle_idx = _ganzhi_to_60cycle_index(gan, zhi)
    xun_start = XUN_START[cycle_idx // 10]
    return list(XUN_KONG[xun_start])