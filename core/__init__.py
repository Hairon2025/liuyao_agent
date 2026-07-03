"""核心业务层：六爻排盘的纯算法（无 LLM 依赖）

公共 API（仅 5 个函数；子模块需按路径导入，例如 `from core.paipan import arrange_hexagram`）：

排盘：
- arrange_hexagram(本卦编码, 起卦时间, 问题) → 完整排盘 dict

起卦（4 种方式）：
- cast_by_manual(numbers)   手动输入爻位编码
- cast_by_time(年, 月, 日, 时) 传统时间起卦
- cast_by_coin()            模拟三枚铜钱抛掷
- cast_by_random()          一键随机生成
"""
from core.paipan import arrange_hexagram
from core.qigua import cast_by_coin, cast_by_manual, cast_by_random, cast_by_time

__all__ = [
    "arrange_hexagram",
    "cast_by_coin",
    "cast_by_manual",
    "cast_by_random",
    "cast_by_time",
]
