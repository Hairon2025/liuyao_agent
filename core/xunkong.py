"""旬空计算（移植自参考项目 main.py）

日干支由调用方通过 `core.calendar.get_ganzhi()` 提供（使用 lunar_python 保证节气精度）。
本模块仅负责：已知日干支 → 旬空地支。
"""
from __future__ import annotations

GAN_ORDER = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
ZHI_ORDER = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

XUN_START = ["甲子", "甲戌", "甲申", "甲午", "甲辰", "甲寅"]
XUN_END = ["癸酉", "癸未", "癸巳", "癸卯", "癸丑", "癸亥"]
XUN_KONG = {
    "甲子": ["戌", "亥"],
    "甲戌": ["申", "酉"],
    "甲申": ["午", "未"],
    "甲午": ["辰", "巳"],
    "甲辰": ["寅", "卯"],
    "甲寅": ["子", "丑"],
}


def get_xunkong(day_ganzhi: str) -> list[str]:
    """根据日干支计算旬空。

    Args:
        day_ganzhi: 日干支，如 "甲子"、"丙午"

    Returns:
        旬空地支列表（如 ["戌", "亥"]）
    """
    if len(day_ganzhi) < 2:
        return ["", ""]

    day_gan = day_ganzhi[0]
    day_zhi = day_ganzhi[1]
    day_gan_idx = GAN_ORDER.index(day_gan)
    day_zhi_idx = ZHI_ORDER.index(day_zhi)
    day_total_idx = day_gan_idx * 12 + day_zhi_idx

    last_idx = len(XUN_START) - 1
    for i in range(len(XUN_START)):
        start_total = GAN_ORDER.index(XUN_START[i][0]) * 12 + ZHI_ORDER.index(XUN_START[i][1])
        end_total = GAN_ORDER.index(XUN_END[i][0]) * 12 + ZHI_ORDER.index(XUN_END[i][1])

        # 甲寅旬特殊处理（跨年循环）
        if i == last_idx:
            if day_total_idx >= start_total or day_total_idx <= end_total:
                return list(XUN_KONG[XUN_START[i]])
        else:
            if start_total <= day_total_idx <= end_total:
                return list(XUN_KONG[XUN_START[i]])

    return ["", ""]
