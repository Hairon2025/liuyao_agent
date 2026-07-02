"""六兽（青龙/朱雀/勾陈/螣蛇/白虎/玄武）配置与计算

六兽起始顺序由日地支决定，每六爻循环一次。
"""
from __future__ import annotations

LIUSHOU: list[str] = ["青龙", "朱雀", "勾陈", "螣蛇", "白虎", "玄武"]
EARTHLY_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]


def get_liushou_order(day_branch: str) -> list[str]:
    """根据日地支获取六爻对应的六兽列表（从初爻到上爻）。"""
    day_idx = EARTHLY_BRANCHES.index(day_branch)
    start_idx = day_idx % 6
    return [LIUSHOU[(start_idx + i) % 6] for i in range(6)]
