"""卦象模块：64 卦数据 + 编码/查询/纳甲

公共 API（推荐使用）：
- parse_hexagram(lines) → HexagramFull  # 一次拿到卦象全部信息
- get_hexagram_palace(lines) → HexagramMeta  # 仅查卦宫
- get_hexagram_trigrams(lines) → (inner, outer)  # 仅查卦位
- encode_hexagram(lines) → list[int]  # 仅做 1-4 → 阴阳 bits 转换

显示常量：
- LINE_NAMES, LINE_SYMBOLS, MOVING_MARK  # 爻型 → 可读文本

子模块（按需使用，不建议直接依赖）：
- data：纯静态数据（64 卦 + 纳甲 4 张表）
- codec：编码/查询底层函数
- display：显示常量
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.core.constants import PALACE_WUXING
from backend.core.hexagrams.codec import (
    encode_hexagram,
    get_hexagram_palace,
    get_hexagram_trigrams,
)
from backend.core.hexagrams.data import (
    HexagramMeta,
    TRIGRAM_BRANCHES_INNER,
    TRIGRAM_BRANCHES_OUTER,
    TRIGRAM_NAME,
    TRIGRAM_STEMS_INNER,
    TRIGRAM_STEMS_OUTER,
)
from backend.core.hexagrams.display import LINE_NAMES, LINE_SYMBOLS, MOVING_MARK


@dataclass(frozen=True)
class HexagramFull:
    """卦象的完整解析结果（一次调用、一次返回）。

    Attributes:
        meta: 卦宫元信息（宫名/世应/卦名/卦类型）
        stems: 6 爻天干（初到上，纳甲）
        branches: 6 爻地支（初到上，纳甲）
        palace_wuxing: 卦宫五行（"我"的五行）
    """
    meta: HexagramMeta
    stems: list[str]
    branches: list[str]
    palace_wuxing: str


def parse_hexagram(lines: list[int]) -> HexagramFull:
    """解析卦象，一次返回完整信息（meta + 纳甲 + 我）。

    这是上层调用方的主要入口；不再需要自己拼 4 张纳甲表。

    Args:
        lines: 6 个爻编码（初爻到上爻，1-4）

    Returns:
        HexagramFull 包含卦宫、纳甲天干地支、卦宫五行

    Raises:
        ValueError: 卦象编码无效或未匹配到 64 卦
    """
    meta = get_hexagram_palace(lines)
    inner, outer = get_hexagram_trigrams(lines)
    stems = TRIGRAM_STEMS_INNER[inner] + TRIGRAM_STEMS_OUTER[outer]
    branches = TRIGRAM_BRANCHES_INNER[inner] + TRIGRAM_BRANCHES_OUTER[outer]
    palace_wuxing = PALACE_WUXING[meta["宫名"]]
    return HexagramFull(
        meta=meta,
        stems=stems,
        branches=branches,
        palace_wuxing=palace_wuxing,
    )


__all__ = [
    "HexagramFull",
    "HexagramMeta",
    "parse_hexagram",
    "get_hexagram_palace",
    "get_hexagram_trigrams",
    "encode_hexagram",
    "TRIGRAM_NAME",
    "LINE_NAMES",
    "LINE_SYMBOLS",
    "MOVING_MARK",
]
