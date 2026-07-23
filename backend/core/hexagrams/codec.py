"""卦象编码 / 解码 / 查询工具

把 1-4 编码的卦象转换为内部表示（阴阳 bits），并查 卦宫 / 卦位 / 纳甲。
这些是底层函数；高层调用请使用 `core.hexagrams.parse_hexagram()`。
"""
from __future__ import annotations

from backend.core.hexagrams.data import (
    HexagramMeta,
    TRIGRAM_BRANCHES_INNER,
    TRIGRAM_BRANCHES_OUTER,
    TRIGRAM_STEMS_INNER,
    TRIGRAM_STEMS_OUTER,
    _HEXAGRAM_DATA,
)


def encode_hexagram(lines: list[int]) -> list[int]:
    """将 1-4 编码转换为阴阳 0/1 列表。

    1=少阴(0), 2=少阳(1), 3=纯阳(1), 4=纯阴(0)
    """
    result = []
    for line in lines:
        if line in (1, 4):
            result.append(0)
        elif line in (2, 3):
            result.append(1)
        else:
            raise ValueError(f"无效爻值：{line}，必须是 1-4")
    return result


def _bits_to_trigram_number(bits: list[int]) -> int:
    """由 3 位的 [下,中,上] 阴阳 bits 反查八卦序数（1-8）。"""
    by_bits: dict[tuple[int, int, int], int] = {
        (1, 1, 1): 1,  # 乾
        (1, 1, 0): 2,  # 兑
        (1, 0, 1): 3,  # 离
        (1, 0, 0): 4,  # 震
        (0, 1, 1): 5,  # 巽
        (0, 1, 0): 6,  # 坎
        (0, 0, 1): 7,  # 艮
        (0, 0, 0): 8,  # 坤
    }
    return by_bits[tuple(bits)]


def get_hexagram_trigrams(lines: list[int]) -> tuple[int, int]:
    """由 6 个爻（1-4 编码）返回 (内卦序数, 外卦序数)。

    返回 (inner, outer)，每个都是 1-8。
    """
    encoded = encode_hexagram(lines)
    inner = _bits_to_trigram_number(encoded[0:3])
    outer = _bits_to_trigram_number(encoded[3:6])
    return inner, outer


def get_hexagram_palace(lines: list[int]) -> HexagramMeta:
    """根据 6 个爻（1-4 编码）查询卦宫、世应、卦名。

    Returns:
        HexagramMeta 拷贝（防止调用方意外修改内部数据）。
    """
    encoded = encode_hexagram(lines)
    key = ",".join(map(str, encoded))
    if key not in _HEXAGRAM_DATA:
        raise ValueError(f"未找到匹配卦象：{lines}（编码：{encoded}）")
    return dict(_HEXAGRAM_DATA[key])  # 返回拷贝，避免外部修改
