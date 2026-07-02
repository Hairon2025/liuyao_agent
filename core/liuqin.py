"""六亲（父母/兄弟/子孙/妻财/官鬼）计算

六亲由"我"（世爻五行）与目标爻五行的生克关系决定。
"""
from __future__ import annotations

# 五行相生（生者 → 被生者）
_GENERATE = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}

# 五行相克（克者 → 被克者）
_CONQUER = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


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
    if _GENERATE.get(wo_wuxing) == target_wuxing:
        return "子孙"

    # 生我者 = 父母
    if _GENERATE.get(target_wuxing) == wo_wuxing:
        return "父母"

    # 我克者 = 妻财
    if _CONQUER.get(wo_wuxing) == target_wuxing:
        return "妻财"

    # 克我者 = 官鬼
    return "官鬼"
