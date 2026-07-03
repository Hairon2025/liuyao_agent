"""动爻/变卦生成（移植自参考项目 main.py）"""
from __future__ import annotations

from typing import List


def generate_changed_hexagram(original: List[int]) -> List[int]:
    """根据本卦生成变卦。

    动爻转换规则：
    - 纯阳(3) → 少阴(1)
    - 纯阴(4) → 少阳(2)
    - 静爻保持不变

    调用方应先用 `has_moving_yao(original)` 守卫；无动爻时本函数返回原卦拷贝。

    Args:
        original: 本卦编码列表（6 个 1-4）

    Returns:
        变卦编码列表
    """
    return [
        1 if line == 3 else
        2 if line == 4 else
        line
        for line in original
    ]


def has_moving_yao(lines: List[int]) -> bool:
    """判断卦象是否有动爻（编码 3 或 4）。"""
    return any(line in (3, 4) for line in lines)


def get_moving_indices(lines: List[int]) -> List[int]:
    """获取所有动爻的位置索引（0=初爻，5=上爻）。"""
    return [i for i, line in enumerate(lines) if line in (3, 4)]


def get_moving_positions(lines: List[int]) -> List[int]:
    """获取动爻位置（1-6，对应初爻到上爻）。"""
    return [i + 1 for i, line in enumerate(lines) if line in (3, 4)]
