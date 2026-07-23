"""六爻排盘主函数（移植自参考项目 main.py:arrange_hexagram）

完整流程（每个阶段对应一个 stage helper）：
1. 时间干支 + 旬空 + 六兽顺序   → _compute_context
2. 本卦 / 变卦解析              → _parse_ben_bian
3. 本卦 / 变卦旺衰得分 + 状态   → _calculate_strengths
4. 组装结构化排盘结果           → _build_single_hexagram_result (x2)

设计目标：
- 纯函数：无 IO、无全局状态
- 返回 dict 而非字符串，方便 API 层组装响应
- 可单测、可缓存
- arrange_hexagram() 只做编排：阶段计算下沉到命名 helper
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict

from backend.core import bianhua, calendar, hexagrams as hex_mod, liuqin, liushen, wangshuai
from backend.core.constants import BRANCH_WUXING
from backend.core.hexagrams import HexagramFull
from backend.core.wangshuai import YaoStrength
from backend.core.xunkong import get_xunkong
from backend.running_data.hexagram_texts import get_hexagram_texts


# ============================================================
# Public TypedDicts (排盘对外输出结构)
# ============================================================


class LineResult(TypedDict):
    """单爻结果"""
    position: int                # 1-6
    liushen: str                 # 六兽
    liuqin: str                  # 六亲
    line_type: str               # 少阴/少阳/纯阴/纯阳
    symbol: str                  # -- -- / -----
    moving_mark: str             # "  →" 或 "   "
    tiangan: str                 # 天干（纳甲）
    dizhi: str                   # 地支
    wuxing: str                  # 五行
    shiying: str                 # 世爻/应爻/---
    is_changing: bool
    score: float
    status: list[str]


class HexagramResult(TypedDict):
    """卦象结果"""
    palace: str                  # 八宫
    gua_type: str                # 本宫/游魂/归魂...
    name: str                    # 卦名
    guaci: str
    yaoci: list[str]             # 6 条爻辞
    shi_yao_position: int        # 1-6
    ying_yao_position: int       # 1-6
    shi_yao_dizhi: str
    ying_yao_dizhi: str
    lines: list[LineResult]


class PaipanResult(TypedDict):
    """完整排盘结果"""
    question: str
    qigua_time: str              # ISO 格式
    ganzhi: dict[str, str]       # year/month/day/hour 地支
    xunkong: list[str]           # 旬空地支
    ben_gua: HexagramResult
    bian_gua: HexagramResult | None
    moving_positions: list[int]  # 动爻位置 1-6


# ============================================================
# Intermediate dataclasses (排盘内部中间态)
# ============================================================


@dataclass(frozen=True)
class PaipanContext:
    """阶段 1-2：时间相关上下文。"""
    ganzhi: dict[str, str]       # {year, month, day, hour} → "丙午" 等
    month_branch: str            # 月支（旺衰计算用）
    day_branch: str              # 日支（旺衰计算用）
    xunkong: list[str]           # 旬空地支
    liushou_order: list[str]     # 六兽顺序（6 个）


@dataclass(frozen=True)
class PaipanStrengths:
    """阶段 5：旺衰计算结果。无变卦时 bian 为 None。"""
    ben: list[YaoStrength]
    bian: list[YaoStrength] | None


# ============================================================
# Stage helpers
# ============================================================


def _compute_context(qigua_time: datetime) -> PaipanContext:
    """阶段 1-2：时间干支 + 旬空 + 六兽顺序。"""
    ganzhi = calendar.get_ganzhi(qigua_time)
    day_ganzhi = ganzhi["day"]
    return PaipanContext(
        ganzhi=ganzhi,
        month_branch=ganzhi["month"][1],
        day_branch=ganzhi["day"][1],
        xunkong=get_xunkong(day_ganzhi),
        liushou_order=liushen.get_liushou_order(ganzhi["day"][1]),
    )


def _parse_ben_bian(
    lines: list[int],
) -> tuple[HexagramFull, HexagramFull | None, list[int] | None]:
    """阶段 3-4：本卦 + 变卦解析。

    Returns:
        (ben, bian, bian_lines)
        - 无动爻时 bian=None, bian_lines=None
        - bian_lines 是变卦的 1-4 编码（旺衰计算 + is_changing 判定需要）
    """
    ben = hex_mod.parse_hexagram(lines)
    if not bianhua.has_moving_yao(lines):
        return ben, None, None
    bian_lines = bianhua.generate_changed_hexagram(lines)
    return ben, hex_mod.parse_hexagram(bian_lines), bian_lines


def _calculate_strengths(
    lines: list[int],
    ben: HexagramFull,
    bian: HexagramFull | None,
    ctx: PaipanContext,
) -> PaipanStrengths:
    """阶段 5：本卦 + 变卦旺衰计算。"""
    moving_indices = bianhua.get_moving_indices(lines)
    ben_strengths = _calculate_single_hex_strengths(
        branches=ben.branches,
        is_original=True,
        lines=lines,
        original_branches=ben.branches,
        changed_branches=bian.branches if bian else None,
        moving_indices=moving_indices,
        ctx=ctx,
    )
    bian_strengths: list[YaoStrength] | None = None
    if bian:
        bian_strengths = _calculate_single_hex_strengths(
            branches=bian.branches,
            is_original=False,
            lines=lines,
            original_branches=ben.branches,
            changed_branches=bian.branches,
            moving_indices=moving_indices,
            ctx=ctx,
        )
    return PaipanStrengths(ben=ben_strengths, bian=bian_strengths)


def _calculate_single_hex_strengths(
    branches: list[str],
    *,
    is_original: bool,
    lines: list[int],
    original_branches: list[str],
    changed_branches: list[str] | None,
    moving_indices: list[int],
    ctx: PaipanContext,
) -> list[YaoStrength]:
    """阶段 5 共享：单卦旺衰计算（本卦或变卦通用）。

    is_original=True 时计算本卦（参考变卦做回头相关判定）；
    is_original=False 时计算变卦（对本位动爻做回头生克）。
    """
    strengths = wangshuai.batch_calculate_strength(
        yao_branches=branches,
        month_branch=ctx.month_branch,
        day_branch=ctx.day_branch,
        changed_branches=changed_branches if is_original else None,
        is_moving_yaos=[line in (3, 4) for line in lines] if is_original else None,
    )
    strengths = wangshuai.check_additional_tomb(
        original_hexagram=lines,
        original_branch=original_branches,
        changed_branch=changed_branches,
        strengths=strengths,
        is_original=is_original,
    )
    if not is_original:
        strengths = wangshuai.check_huitou(
            original_branch=original_branches,
            changed_branch=changed_branches,
            moving_indices=moving_indices,
            changed_strength=strengths,
        )
    return strengths


def _build_line_result(
    line_value: int,
    idx: int,
    tiangan: str,
    dizhi: str,
    wuxing: str,
    shi_yao_idx: int,
    ying_yao_idx: int,
    liushou_order: list[str],
    liqin_str: str,
    strength: YaoStrength,
) -> LineResult:
    """组装单爻结果。"""
    if idx == shi_yao_idx:
        shiying = "世爻"
    elif idx == ying_yao_idx:
        shiying = "应爻"
    else:
        shiying = "---"

    return {
        "position": idx + 1,
        "liushen": liushou_order[idx],
        "liuqin": liqin_str,
        "line_type": hex_mod.LINE_NAMES[line_value],
        "symbol": hex_mod.LINE_SYMBOLS[line_value],
        "moving_mark": hex_mod.MOVING_MARK[line_value],
        "tiangan": tiangan,
        "dizhi": dizhi,
        "wuxing": wuxing,
        "shiying": shiying,
        "is_changing": line_value in (3, 4),
        "score": strength["score"],
        "status": list(strength["status"]),
    }


def _build_single_hexagram_result(
    lines: list[int],
    hex_full: HexagramFull,
    strengths: list[YaoStrength],
    liushou_order: list[str],
    *,
    wo_wuxing: str,
) -> HexagramResult:
    """阶段 6：组装单卦（本卦或变卦）的对外结构。

    Args:
        lines: 1-4 编码（用于查 LINE_NAMES/SYMBOLS/MOVING_MARK + is_changing）
        hex_full: 已解析的卦象（meta + 纳甲 + 卦宫五行）
        strengths: 已计算的旺衰列表（6 个爻）
        liushou_order: 六兽顺序（来自 ctx）
        wo_wuxing: "我"的五行，用于六亲映射。
            本卦 = hex_full.palace_wuxing；
            变卦 = 沿用本卦（由调用方显式传入）。
    """
    texts = get_hexagram_texts(hex_full.meta["卦名"])
    shi_yao_idx = hex_full.meta["世爻索引"]
    ying_yao_idx = hex_full.meta["应爻索引"]

    line_results: list[LineResult] = []
    for i in range(6):
        dizhi = hex_full.branches[i]
        wuxing = BRANCH_WUXING[dizhi]
        liqin_str = liuqin.get_liqin(wo_wuxing, wuxing) if wo_wuxing else ""
        line_results.append(
            _build_line_result(
                line_value=lines[i],
                idx=i,
                tiangan=hex_full.stems[i],
                dizhi=dizhi,
                wuxing=wuxing,
                shi_yao_idx=shi_yao_idx,
                ying_yao_idx=ying_yao_idx,
                liushou_order=liushou_order,
                liqin_str=liqin_str,
                strength=strengths[i],
            )
        )

    return {
        "palace": hex_full.meta["宫名"],
        "gua_type": hex_full.meta["卦类型"],
        "name": hex_full.meta["卦名"],
        "guaci": texts.get("卦辞", ""),
        "yaoci": list(texts.get("爻辞", [])),
        "shi_yao_position": shi_yao_idx + 1,
        "ying_yao_position": ying_yao_idx + 1,
        "shi_yao_dizhi": hex_full.branches[shi_yao_idx],
        "ying_yao_dizhi": hex_full.branches[ying_yao_idx],
        "lines": line_results,
    }


# ============================================================
# Main: arrange_hexagram (编排 5 个 stage)
# ============================================================


def arrange_hexagram(
    original_hexagram: list[int],
    qigua_time: datetime,
    question: str,
) -> PaipanResult:
    """六爻排盘主函数。

    Args:
        original_hexagram: 本卦编码列表，6 个 1-4（从初爻到上爻）
            1=少阴, 2=少阳, 3=纯阳(动), 4=纯阴(动)
        qigua_time: 起卦时间
        question: 起卦问题/原因

    Returns:
        结构化排盘结果 dict
    """
    # 阶段 1-2: 时间上下文
    ctx = _compute_context(qigua_time)

    # 阶段 3-4: 本卦 + 变卦解析
    ben, bian, bian_lines = _parse_ben_bian(original_hexagram)

    # 阶段 5: 旺衰（本卦 + 变卦）
    strengths = _calculate_strengths(original_hexagram, ben, bian, ctx)

    # 阶段 6: 组装结果
    ben_gua = _build_single_hexagram_result(
        lines=original_hexagram,
        hex_full=ben,
        strengths=strengths.ben,
        liushou_order=ctx.liushou_order,
        wo_wuxing=ben.palace_wuxing,
    )
    bian_gua: HexagramResult | None = None
    if bian and bian_lines and strengths.bian:
        bian_gua = _build_single_hexagram_result(
            lines=bian_lines,
            hex_full=bian,
            strengths=strengths.bian,
            liushou_order=ctx.liushou_order,
            wo_wuxing=ben.palace_wuxing,  # 变卦沿用本卦的"我"（卦宫五行）
        )

    return {
        "question": question,
        "qigua_time": qigua_time.isoformat(),
        "ganzhi": ctx.ganzhi,
        "xunkong": ctx.xunkong,
        "ben_gua": ben_gua,
        "bian_gua": bian_gua,
        "moving_positions": bianhua.get_moving_positions(original_hexagram),
    }