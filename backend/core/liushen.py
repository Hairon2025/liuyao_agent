"""六兽（青龙/朱雀/勾陈/螣蛇/白虎/玄武）配置与计算

六兽起始顺序由日地支决定，每六爻循环一次。
"""
from __future__ import annotations

from backend.core.constants import ZHI_ORDER

LIUSHOU: list[str] = ["青龙", "朱雀", "勾陈", "螣蛇", "白虎", "玄武"]


def get_liushou_order(day_branch: str) -> list[str]:
    """根据日地支获取六爻对应的六兽列表（从初爻到上爻）。"""
    day_idx = ZHI_ORDER.index(day_branch)
    start_idx = day_idx % 6
    return [LIUSHOU[(start_idx + i) % 6] for i in range(6)]
