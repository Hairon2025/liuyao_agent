"""起卦算法（手动 / 时间 / 铜钱 / 随机）

卦象编码（与参考项目保持一致）：
- 1 = 少阴（-- --）
- 2 = 少阳（-----）
- 3 = 纯阳（动爻，→ 变少阴）
- 4 = 纯阴（动爻，→ 变少阳）
"""
from __future__ import annotations

import random
from datetime import datetime
from enum import Enum
from typing import List


class QiguaMethod(str, Enum):
    """起卦方式"""
    MANUAL = "manual"
    COIN = "coin"
    TIME = "time"
    RANDOM = "random"


# 八卦序数：1=乾, 2=兑, 3=离, 4=震, 5=巽, 6=坎, 7=艮, 8=坤
TRIGRAMS_BY_NUMBER: dict[int, list[int]] = {
    1: [1, 1, 1],  # 乾
    2: [1, 1, 0],  # 兑
    3: [1, 0, 1],  # 离
    4: [1, 0, 0],  # 震
    5: [0, 1, 1],  # 巽
    6: [0, 1, 0],  # 坎
    7: [0, 0, 1],  # 艮
    8: [0, 0, 0],  # 坤
}


def _trigram_to_yinyang(trigram_number: int) -> list[int]:
    """根据卦序数（1-8）返回三爻阴阳列表（从下到上）。"""
    if trigram_number == 0:
        trigram_number = 8
    return TRIGRAMS_BY_NUMBER[trigram_number]


def _make_line(yang: bool, is_moving: bool) -> int:
    """根据阴阳和动静生成 1-4 编码。"""
    if yang and is_moving:
        return 3  # 纯阳
    if not yang and is_moving:
        return 4  # 纯阴
    if yang:
        return 2  # 少阳
    return 1  # 少阴


def cast_by_time(dt: datetime) -> List[int]:
    """时间起卦（传统方法）。

    上卦 = (年数 + 月数 + 日数) % 8
    下卦 = (年数 + 月数 + 日数 + 时辰数) % 8
    动爻 = (年数 + 月数 + 日数 + 时辰数) % 6
    注：传统使用农历年数（后天八卦序），此处用公历作近似

    Args:
        dt: 起卦时间

    Returns:
        6 个爻的列表（从初爻到上爻）
    """
    year = dt.year
    month = dt.month
    day = dt.day
    hour = dt.hour

    upper_sum = year + month + day
    lower_sum = upper_sum + hour

    upper_num = upper_sum % 8
    lower_num = lower_sum % 8
    moving_pos = lower_sum % 6  # 1-6，动爻位置

    upper_trigram = _trigram_to_yinyang(upper_num)
    lower_trigram = _trigram_to_yinyang(lower_num)

    # 组合卦象：下卦在下 3 爻，上卦在上 3 爻
    # trigram_to_yinyang 返回 [下爻, 中爻, 上爻]
    lines: list[int] = []
    for i in range(3):
        lines.append(_make_line(lower_trigram[i] == 1, is_moving=(moving_pos == i + 1)))
    for i in range(3):
        lines.append(_make_line(upper_trigram[i] == 1, is_moving=(moving_pos == i + 4)))

    return lines


def cast_by_manual(numbers: List[int]) -> List[int]:
    """手动起卦。

    Args:
        numbers: 6 个 1-4 的数字（从初爻到上爻）
            1=少阴, 2=少阳, 3=纯阳(动), 4=纯阴(动)

    Returns:
        6 个爻的列表
    """
    if len(numbers) != 6:
        raise ValueError(f"需要 6 个数字，当前 {len(numbers)} 个")
    for n in numbers:
        if n not in (1, 2, 3, 4):
            raise ValueError(f"无效爻值：{n}，必须是 1-4")
    return list(numbers)


def cast_by_coin() -> List[int]:
    """铜钱起卦：模拟三枚铜钱抛掷六次。

    三枚铜钱（字=阴，花=阳）：
    - 三字 → 老阴 (4, 动爻)
    - 二字一花 → 少阳 (2)
    - 一字二花 → 少阴 (1)
    - 三花 → 老阳 (3, 动爻)

    Returns:
        6 个爻的列表（从初爻到上爻）
    """
    lines: list[int] = []
    for _ in range(6):
        # 每个铜钱 0=字(阴), 1=花(阳)
        coins = [random.randint(0, 1) for _ in range(3)]
        yang_count = sum(coins)
        if yang_count == 0:    # 三字
            lines.append(4)
        elif yang_count == 1:  # 二字一花
            lines.append(2)
        elif yang_count == 2:  # 一字二花
            lines.append(1)
        else:                  # 三花
            lines.append(3)
    return lines


def cast_by_random() -> List[int]:
    """随机起卦：一键生成。"""
    return [random.randint(1, 4) for _ in range(6)]
