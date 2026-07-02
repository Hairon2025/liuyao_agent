"""公历转八字工具模块（迁移自根目录 solar_to_bazi.py）"""
from lunar_python import Solar


def solar_to_bazi(solar_year: int, solar_month: int, solar_day: int, hour: int) -> dict:
    """将公历日期转换为八字四柱。

    Args:
        solar_year: 公历年
        solar_month: 公历月
        solar_day: 公历日
        hour: 时辰（0-23）

    Returns:
        dict: 包含 year/month/day/hour 四柱的字典
    """
    solar = Solar.fromYmdHms(solar_year, solar_month, solar_day, hour, 0, 0)
    lunar = solar.getLunar()
    bazi = lunar.getEightChar()
    return {
        "year": bazi.getYear(),
        "month": bazi.getMonth(),
        "day": bazi.getDay(),
        "hour": bazi.getTime(),
    }


if __name__ == "__main__":
    result = solar_to_bazi(2026, 7, 2, 11)
    print(f"年柱：{result['year']}, 月柱：{result['month']}, 日柱：{result['day']}, 时柱：{result['hour']}")
