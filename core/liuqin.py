"""六亲（父母/兄弟/子孙/妻财/官鬼）计算

六亲由"我"（世爻五行）与目标爻五行的生克关系决定。
"""
from __future__ import annotations

from core.constants import CONQUER_WUXING, GENERATE_WUXING


def get_liqin(wo_wuxing: str, target_wuxing: str) -> str:
    """根据"我"五行与目标五行计算六亲。

    Args:
        wo_wuxing: 世爻五行（木火土金水）
        target_wuxing: 目标爻五行

    Returns:
        六亲名称：父母 / 兄弟 / 子孙 / 妻财 / 官鬼
    """
    if not wo_wuxing or not target_wuxing:
        return ""

    if target_wuxing == wo_wuxing:
        return "兄弟"

    # 我生者 = 子孙
    if GENERATE_WUXING.get(wo_wuxing) == target_wuxing:
        return "子孙"

    # 生我者 = 父母
    if GENERATE_WUXING.get(target_wuxing) == wo_wuxing:
        return "父母"

    # 我克者 = 妻财
    if CONQUER_WUXING.get(wo_wuxing) == target_wuxing:
        return "妻财"

    # 克我者 = 官鬼
    return "官鬼"
