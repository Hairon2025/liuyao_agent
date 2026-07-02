"""动爻/变卦生成（移植自参考项目 main.py）"""
from __future__ import annotations

from typing import List


def generate_changed_hexagram(original: List[int]) -> List[int]:
    """根据本卦生成变卦。

    动爻转换规则：
    - 纯阳(3) → 少阴(1)
    - 纯阴(4) → 少阳(2)
    - 静爻保持不变

    Args:
        original: 本卦编码列表（6 个 1-4）

    Returns:
        变卦编码列表
    """
    changed = []
    for line in original:
        if line == 3:
            changed.append(1)
        elif line == 4:
            changed.append(2)
        else:
            changed.append(line)

    # 兜底：若变卦与本卦完全相同（无动爻情况下已被前面逻辑过滤）
    if changed == original:
        for i, line in enumerate(original):
            if line == 3:
                changed[i] = 2
                break
            if line == 4:
                changed[i] = 1
                break

    return changed


def has_moving_yao(lines: List[int]) -> bool:
    """判断卦象是否有动爻（编码 3 或 4）。"""
    return any(line in (3, 4) for line in lines)


def get_moving_indices(lines: List[int]) -> List[int]:
    """获取所有动爻的位置索引（0=初爻，5=上爻）。"""
    return [i for i, line in enumerate(lines) if line in (3, 4)]


def get_moving_positions(lines: List[int]) -> List[int]:
    """获取动爻位置（1-6，对应初爻到上爻）。"""
    return [i + 1 for i, line in enumerate(lines) if line in (3, 4)]
