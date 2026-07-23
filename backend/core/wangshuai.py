"""爻旺衰判断（移植自参考项目 wangshuai.py）

计算每一爻的旺衰得分及状态（月扶、日生、入墓、暗动、化绝等）。
"""
from __future__ import annotations

from typing import TypedDict

from backend.core.constants import (
    BRANCH_WUXING,
    COMBINE_BRANCH,
    CONFLICT_BRANCH,
    CONQUER_WUXING,
    EXTINCTION,
    GENERATE_WUXING,
    IMPERIAL_WANG,
    POSITION_NAMES,
    TOMB_BRANCH,
)


class YaoStrength(TypedDict):
    score: float
    status: list[str]


def _to_list(v: list[str] | str) -> list[str]:
    return v if isinstance(v, list) else [v]


def get_seasonal_status(month_branch: str) -> dict[str, str]:
    """根据月令地支返回五行四季状态（旺相休囚死）。"""
    if month_branch in ("寅", "卯"):
        return {"木": "旺", "火": "相", "水": "休", "金": "囚", "土": "死"}
    if month_branch in ("巳", "午"):
        return {"火": "旺", "土": "相", "木": "休", "水": "囚", "金": "死"}
    if month_branch in ("申", "酉"):
        return {"金": "旺", "水": "相", "土": "休", "火": "囚", "木": "死"}
    if month_branch in ("亥", "子"):
        return {"水": "旺", "木": "相", "金": "休", "土": "囚", "火": "死"}
    if month_branch in ("辰", "未", "戌", "丑"):
        return {"土": "旺", "金": "相", "火": "休", "木": "囚", "水": "死"}
    return {}


def calculate_yao_strength(
    yao_branch: str,
    month_branch: str,
    day_branch: str,
    changed_yao_branch: str | None = None,
    is_moving_yao: bool = False,
) -> YaoStrength:
    """计算单爻旺衰得分及状态。"""
    score = 0.0
    status: list[str] = []
    yao_wuxing = BRANCH_WUXING[yao_branch]
    month_wuxing = BRANCH_WUXING[month_branch]
    day_wuxing = BRANCH_WUXING[day_branch]

    # 1. 月建/日建
    if yao_branch == month_branch:
        score += 2.0
        status.append("月建")
    if yao_branch == day_branch:
        score += 1.5
        status.append("日建")

    # 2. 月合
    if COMBINE_BRANCH.get(yao_branch) == month_branch:
        month_conquer_yao = CONQUER_WUXING.get(month_wuxing) == yao_wuxing
        yao_conquer_month = CONQUER_WUXING.get(yao_wuxing) == month_wuxing
        if not (month_conquer_yao or yao_conquer_month):
            score += 1.5
            status.append("合旺")
        else:
            score -= 0.5
            status.append("月合克")

    # 3. 日合
    if COMBINE_BRANCH.get(yao_branch) == day_branch:
        day_conquer_yao = CONQUER_WUXING.get(day_wuxing) == yao_wuxing
        yao_conquer_day = CONQUER_WUXING.get(yao_wuxing) == day_wuxing
        if not (day_conquer_yao or yao_conquer_day):
            score += 1.5
            status.append("合绊")
        else:
            score -= 0.5
            status.append("日合克")

    # 4. 月生/日生
    if GENERATE_WUXING.get(month_wuxing) == yao_wuxing:
        score += 1.5
        status.append("月生")
    if GENERATE_WUXING.get(day_wuxing) == yao_wuxing:
        score += 1.5
        status.append("日生")

    # 5. 月扶/日扶
    if month_wuxing == yao_wuxing and yao_branch != month_branch:
        score += 1.0
        status.append("月扶")
    if day_wuxing == yao_wuxing and yao_branch != day_branch:
        score += 0.5
        status.append("日扶")

    # 6. 月破
    if CONFLICT_BRANCH.get(yao_branch) == month_branch:
        score -= 2.0
        status.append("月破")

    # 7. 月克/日克
    if CONQUER_WUXING.get(month_wuxing) == yao_wuxing:
        score -= 1.0
        status.append("月克")
    if CONQUER_WUXING.get(day_wuxing) == yao_wuxing:
        score -= 1.0
        status.append("日克")

    # 8. 日散（与日冲且不旺）
    is_day_conflict = CONFLICT_BRANCH.get(yao_branch) == day_branch
    if is_day_conflict and score < 0:
        score -= 1.5
        status.append("日散")

    # 9. 帝旺（日令为爻的帝旺位）
    diwang_branches = _to_list(IMPERIAL_WANG[yao_wuxing])
    if day_branch in diwang_branches:
        score += 1.0
        status.append("帝旺")

    # 10. 季节休囚
    seasonal_status = get_seasonal_status(month_branch)
    yao_season = seasonal_status.get(yao_wuxing)
    if yao_season in ("休", "囚", "死"):
        score -= 1.5
        status.append(f"休囚（{yao_season}）")

    # 11. 入墓
    tomb_branches = _to_list(TOMB_BRANCH[yao_wuxing])
    tomb_source: list[str] = []
    if month_branch in tomb_branches:
        tomb_source.append("月墓")
    if day_branch in tomb_branches:
        tomb_source.append("日墓")
    if tomb_source:
        score = -0.1
        status.append(f"入{'/'.join(tomb_source)}")

    # 12. 绝地（静爻处于日令绝位）
    if not is_moving_yao and day_branch == EXTINCTION[yao_wuxing]:
        score -= 0.5
        status.append("绝地")

    # 13. 化绝（动爻化出绝位变爻）
    if changed_yao_branch and is_moving_yao and changed_yao_branch == EXTINCTION[yao_wuxing]:
        score -= 1.0
        status.append("化绝")

    # 14. 暗动（与日冲且得分≥0）
    if is_day_conflict and score >= 0:
        status.append("暗动")

    return {"score": round(score, 2), "status": status}


def batch_calculate_strength(
    yao_branches: list[str],
    month_branch: str,
    day_branch: str,
    changed_branches: list[str | None] | None = None,
    is_moving_yaos: list[bool] | None = None,
) -> list[YaoStrength]:
    """批量计算六爻旺衰。"""
    changed_branches = changed_branches or [None] * 6
    is_moving_yaos = is_moving_yaos or [False] * 6

    results: list[YaoStrength] = []
    for i in range(6):
        changed = changed_branches[i] if i < len(changed_branches) else None
        moving = is_moving_yaos[i] if i < len(is_moving_yaos) else False
        results.append(
            calculate_yao_strength(
                yao_branch=yao_branches[i],
                month_branch=month_branch,
                day_branch=day_branch,
                changed_yao_branch=changed,
                is_moving_yao=moving,
            )
        )
    return results


def check_additional_tomb(
    original_hexagram: list[int],
    original_branch: list[str],
    changed_branch: list[str] | None,
    strengths: list[YaoStrength],
    is_original: bool = True,
) -> list[YaoStrength]:
    """检查入墓扩展状态（入动爻墓/变爻墓）。"""
    moving_indices = [i for i, line in enumerate(original_hexagram) if line in (3, 4)]

    for i in range(6):
        yao_branch = original_branch[i] if is_original else (changed_branch[i] if changed_branch else "")
        yao_wuxing = BRANCH_WUXING[yao_branch]
        tomb_branches = _to_list(TOMB_BRANCH[yao_wuxing])

        # 静爻入动爻墓
        if is_original and original_hexagram[i] not in (3, 4):
            for idx in moving_indices:
                mb = original_branch[idx]
                if mb in tomb_branches:
                    strengths[i]["status"].append(f"入{POSITION_NAMES[idx]}墓")

        # 动爻入变爻墓
        if is_original and original_hexagram[i] in (3, 4):
            if changed_branch and i < len(changed_branch):
                if changed_branch[i] in tomb_branches:
                    strengths[i]["status"].append("入变爻墓")

        # 变卦中对应本卦动爻的位置 → 入本位动爻墓
        if not is_original and i in moving_indices:
            if original_branch[i] in tomb_branches:
                strengths[i]["status"].append("入本位动爻墓")

    return strengths


def check_huitou(
    original_branch: list[str],
    changed_branch: list[str],
    moving_indices: list[int],
    changed_strength: list[YaoStrength],
) -> list[YaoStrength]:
    """回头生克判断（变爻对本位动爻的影响）。"""
    for i in moving_indices:
        original_wuxing = BRANCH_WUXING[original_branch[i]]
        changed_wuxing = BRANCH_WUXING[changed_branch[i]]
        if GENERATE_WUXING.get(changed_wuxing) == original_wuxing:
            changed_strength[i]["status"].append("回头生")
        if CONQUER_WUXING.get(changed_wuxing) == original_wuxing:
            changed_strength[i]["status"].append("回头克")
    return changed_strength
