"""核心业务层：六爻排盘的纯算法（无 LLM 依赖）

公共 API：
- calendar: 地支计算
- hexagrams: 64 卦卦宫数据 + 编码转换
- wangshuai: 旺衰计算
- xunkong: 旬空计算
- liushen: 六兽
- liuqin: 六亲
- bianhua: 动爻/变卦生成
- paipan: 排盘主函数
- qigua: 起卦算法
"""
from core import bianhua, calendar, hexagrams, liuqin, liushen, paipan, qigua, wangshuai, xunkong
from core.paipan import arrange_hexagram
from core.qigua import cast_by_coin, cast_by_manual, cast_by_random, cast_by_time

__all__ = [
    "arrange_hexagram",
    "cast_by_coin",
    "cast_by_manual",
    "cast_by_random",
    "cast_by_time",
    "bianhua",
    "calendar",
    "hexagrams",
    "liuqin",
    "liushen",
    "paipan",
    "qigua",
    "wangshuai",
    "xunkong",
]
