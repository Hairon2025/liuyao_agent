"""干支计算（公历 → 年月日时四柱干支）

基于 lunar_python 库精确计算。节气按精确时刻划分（立春分界年柱、惊蛰分界月柱等），
日柱精确到天、时柱精确到时辰。
"""
from __future__ import annotations

from datetime import datetime

from utils.bazi import solar_to_bazi


def get_ganzhi(dt: datetime) -> dict[str, str]:
    """一次性返回年月日时四柱干支。

    Returns:
        dict，键为 year/month/day/hour，值为"天干+地支"完整字符串（如"丙午"）。
    """
    return solar_to_bazi(dt.year, dt.month, dt.day, dt.hour)


def get_year_ganzhi(dt: datetime) -> str:
    """返回年柱干支（年柱以立春为界）。"""
    return get_ganzhi(dt)["year"]


def get_month_ganzhi(dt: datetime) -> str:
    """返回月柱干支（以节气为界）。"""
    return get_ganzhi(dt)["month"]


def get_day_ganzhi(dt: datetime) -> str:
    """返回日柱干支（以子时为界）。"""
    return get_ganzhi(dt)["day"]


def get_hour_ganzhi(dt: datetime) -> str:
    """返回时柱干支。"""
    return get_ganzhi(dt)["hour"]