"""六爻排盘主函数（移植自参考项目 main.py:arrange_hexagram）

完整流程：
1. 计算时间地支 + 旬空
2. 计算六兽顺序
3. 识别本卦（卦宫、世应、卦名）
4. 生成变卦
5. 计算本卦/变卦每爻旺衰得分与状态
6. 返回结构化排盘结果

设计目标：
- 纯函数：无 IO、无全局状态
- 返回 dict 而非字符串，方便 API 层组装响应
- 可单测、可缓存
"""
from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from core import bianhua, calendar, hexagrams as hex_mod, liuqin, liushen, wangshuai
from core.wangshuai import YaoStrength
from core.xunkong import get_xunkong


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


def _build_hexagram_result(
    lines: list[int],
    stems: list[str],
    branches: list[str],
    liushou_order: list[str],
    wo_wuxing: str | None,
    strengths: list[YaoStrength],
    palace: str,
    gua_type: str,
    name: str,
    shi_yao_idx: int,
    ying_yao_idx: int,
    texts: dict,
) -> HexagramResult:
    """组装单卦（本卦或变卦）结果。"""
    line_results: list[LineResult] = []
    for i in range(6):
        tiangan = stems[i]
        dizhi = branches[i]
        wuxing = hex_mod.BRANCH_WUXING[dizhi]
        liqin_str = liuqin.get_liqin(wo_wuxing, wuxing) if wo_wuxing else ""
        line_results.append(
            _build_line_result(
                line_value=lines[i],
                idx=i,
                tiangan=tiangan,
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
        "palace": palace,
        "gua_type": gua_type,
        "name": name,
        "guaci": texts.get("卦辞", ""),
        "yaoci": list(texts.get("爻辞", [])),
        "shi_yao_position": shi_yao_idx + 1,
        "ying_yao_position": ying_yao_idx + 1,
        "shi_yao_dizhi": branches[shi_yao_idx],
        "ying_yao_dizhi": branches[ying_yao_idx],
        "lines": line_results,
    }


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
    # 1. 时间干支（lunar_python 精确节气计算） + 旬空
    ganzhi = calendar.get_ganzhi(qigua_time)
    day_ganzhi = ganzhi["day"]                       # e.g., "丁丑"
    month_branch = ganzhi["month"][1]                # 提取地支
    day_branch = ganzhi["day"][1]                    # 提取地支
    xunkong = get_xunkong(day_ganzhi)

    # 2. 六兽顺序
    liushou_order = liushen.get_liushou_order(day_branch)

    # 3. 本卦信息
    ben_info = hex_mod.get_hexagram_palace(original_hexagram)
    ben_palace = ben_info["宫名"]
    ben_gua_type = ben_info["卦类型"]
    ben_name = ben_info["卦名"]
    ben_shi_idx = ben_info["世爻索引"]
    ben_ying_idx = ben_info["应爻索引"]
    ben_inner, ben_outer = hex_mod.get_hexagram_trigrams(original_hexagram)
    ben_branches = hex_mod.TRIGRAM_BRANCHES_INNER[ben_inner] + hex_mod.TRIGRAM_BRANCHES_OUTER[ben_outer]
    ben_stems = hex_mod.TRIGRAM_STEMS_INNER[ben_inner] + hex_mod.TRIGRAM_STEMS_OUTER[ben_outer]
    # "我"按卦宫五行取（卦宫固定则六亲映射稳定，本卦/变卦统一规则）
    ben_shi_wuxing = hex_mod.PALACE_WUXING[ben_palace]

    # 4. 变卦
    moving_positions = bianhua.get_moving_positions(original_hexagram)
    has_moving = len(moving_positions) > 0

    bian_lines: list[int] | None = None
    bian_branches: list[str] | None = None
    bian_stems: list[str] | None = None
    bian_info = None
    if has_moving:
        bian_lines = bianhua.generate_changed_hexagram(original_hexagram)
        bian_info = hex_mod.get_hexagram_palace(bian_lines)
        bian_inner, bian_outer = hex_mod.get_hexagram_trigrams(bian_lines)
        bian_branches = hex_mod.TRIGRAM_BRANCHES_INNER[bian_inner] + hex_mod.TRIGRAM_BRANCHES_OUTER[bian_outer]
        bian_stems = hex_mod.TRIGRAM_STEMS_INNER[bian_inner] + hex_mod.TRIGRAM_STEMS_OUTER[bian_outer]



    # 5. 标记动爻
    is_moving = [line in (3, 4) for line in original_hexagram]
    moving_indices = bianhua.get_moving_indices(original_hexagram)

    # 6. 计算本卦旺衰
    ben_strengths = wangshuai.batch_calculate_strength(
        yao_branches=ben_branches,
        month_branch=month_branch,
        day_branch=day_branch,
        changed_branches=bian_branches,
        is_moving_yaos=is_moving,
    )
    ben_strengths = wangshuai.check_additional_tomb(
        original_hexagram=original_hexagram,
        original_branch=ben_branches,
        changed_branch=bian_branches,
        strengths=ben_strengths,
        is_original=True,
    )

    # 7. 计算变卦旺衰
    bian_strengths: list[YaoStrength] | None = None
    if has_moving and bian_lines and bian_branches:
        bian_strengths = wangshuai.batch_calculate_strength(
            yao_branches=bian_branches,
            month_branch=month_branch,
            day_branch=day_branch,
            changed_branches=None,
        )
        bian_strengths = wangshuai.check_additional_tomb(
            original_hexagram=original_hexagram,
            original_branch=ben_branches,
            changed_branch=bian_branches,
            strengths=bian_strengths,
            is_original=False,
        )
        bian_strengths = wangshuai.check_huitou(
            original_branch=ben_branches,
            changed_branch=bian_branches,
            moving_indices=moving_indices,
            changed_strength=bian_strengths,
        )

    # 8. 加载卦辞爻辞
    from data.hexagram_texts import get_hexagram_texts

    ben_texts = get_hexagram_texts(ben_name)
    bian_texts = get_hexagram_texts(bian_info["卦名"]) if bian_info else {"卦辞": "", "爻辞": []}

    # 9. 变卦沿用本卦的"我"（卦宫五行），不再单独取变卦卦宫
    bian_shi_idx = bian_info["世爻索引"] if bian_info else None

    # 10. 组装结果
    ben_gua = _build_hexagram_result(
        lines=original_hexagram,
        stems=ben_stems,
        branches=ben_branches,
        liushou_order=liushou_order,
        wo_wuxing=ben_shi_wuxing,
        strengths=ben_strengths,
        palace=ben_palace,
        gua_type=ben_gua_type,
        name=ben_name,
        shi_yao_idx=ben_shi_idx,
        ying_yao_idx=ben_ying_idx,
        texts=ben_texts,
    )

    bian_gua: HexagramResult | None = None
    if has_moving and bian_lines and bian_branches and bian_info and bian_strengths:
        bian_gua = _build_hexagram_result(
            lines=bian_lines,
            stems=bian_stems,
            branches=bian_branches,
            liushou_order=liushou_order,
            wo_wuxing=ben_shi_wuxing,  # 变卦沿用本卦的"我"（卦宫五行）
            strengths=bian_strengths,
            palace=bian_info["宫名"],
            gua_type=bian_info["卦类型"],
            name=bian_info["卦名"],
            shi_yao_idx=bian_shi_idx if bian_shi_idx is not None else 0,
            ying_yao_idx=(bian_shi_idx + 3) % 6 if bian_shi_idx is not None else 3,
            texts=bian_texts,
        )

    return {
        "question": question,
        "qigua_time": qigua_time.isoformat(),
        "ganzhi": ganzhi,
        "xunkong": xunkong,
        "ben_gua": ben_gua,
        "bian_gua": bian_gua,
        "moving_positions": moving_positions,
    }
