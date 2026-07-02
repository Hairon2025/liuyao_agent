"""将排盘结果渲染为格式化的 Markdown

输出结构参考 六爻模版.md：
- 起卦信息（时间、问题）
- 时间地支与旬空
- 本卦（含卦辞 + 六爻表）
- 变卦（含卦辞 + 六爻表，可选）
- 动爻汇总
- 备注（地支关系、五行长生等参考信息）
- 免责声明
"""
from __future__ import annotations

from typing import Iterable

from schema.divination import DivinationResponse, HexagramInfo, LineInfo


# ----- 参考备忘信息（与原参考项目一致）-----
_REFERENCE_NOTES = """\
### 地支相合
子丑合土局（水）；寅亥合木局；卯戌合火局；辰酉合金局；巳申合水局；午未合土局

### 地支相冲
子午；丑未；寅申；卯酉；辰戌；巳亥

### 五行长生
- 木长生在亥，旺在卯，墓在未，绝于申
- 火长生在寅，旺在午，墓在戌，绝于亥
- 金长生在巳，旺在酉，墓在丑，绝于寅
- 水长生在申，旺在子，墓在辰，绝于巳
- 土随火行：长生在寅，绝于亥；墓于四墓库，旺于四墓库

### 季节旺衰
| 季节 | 旺 | 相 | 休 | 囚 | 死 |
|---|---|---|---|---|---|
| 春季 | 木 | 火 | 水 | 金 | 土 |
| 夏季 | 火 | 土 | 木 | 水 | 金 |
| 秋季 | 金 | 水 | 土 | 火 | 木 |
| 冬季 | 水 | 木 | 金 | 土 | 火 |
| 季末 | 土 | 金 | 火 | 木 | 水 |

> 旺衰得分仅作最基础参考。
"""

_DISCLAIMER = "本结果仅供文化娱乐参考，不构成任何人生决策依据。"


def _format_line_table_row(line: LineInfo) -> str:
    """格式化单爻表格行。"""
    changing = "动" if line.is_changing else "  "
    status = "、".join(line.status) if line.status else "—"
    shiying = line.shiying if line.shiying != "---" else "—"
    return (
        f"| {line.line_type} | {line.liushen} | {line.liuqin or '—'} | "
        f"{line.symbol}{line.moving_mark.strip()} | "
        f"{line.tiangan} | {line.dizhi}({line.wuxing}) | "
        f"{changing} | {shiying} | {line.score:+.1f} | {status} |"
    )


def _format_hexagram_section(gua: HexagramInfo) -> list[str]:
    """格式化单卦（本卦或变卦）的 Markdown 段落。"""
    lines: list[str] = []
    lines.append(f"### {gua.palace} {gua.gua_type}：{gua.name}")
    lines.append("")
    lines.append(f"**卦辞**：{gua.guaci}")
    lines.append("")
    lines.append(
        f"**世爻**：{gua.shi_yao_position}爻（{gua.shi_yao_dizhi}）  "
        f"**应爻**：{gua.ying_yao_position}爻（{gua.ying_yao_dizhi}）"
    )
    lines.append("")
    lines.append("| 爻型 | 六神 | 六亲 | 卦象 | 天干 | 地支(五行) | 动爻 | 世应 | 旺衰得分 | 状态 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    # 从上爻到初爻输出（传统六爻表阅读顺序）
    sorted_lines = sorted(gua.lines, key=lambda x: x.position, reverse=True)
    for line in sorted_lines:
        lines.append(_format_line_table_row(line))
    lines.append("")
    return lines


def _format_moving_lines(moving_positions: Iterable[int]) -> list[str]:
    positions = sorted(moving_positions)
    if not positions:
        return ["_（无动爻，本卦即为所测之卦）_", ""]
    yao_names = ["", "初爻", "二爻", "三爻", "四爻", "五爻", "上爻"]
    names = [yao_names[p] for p in positions if 1 <= p <= 6]
    return [f"动爻位置：**{'、'.join(names)}**", ""]


def to_markdown(response: DivinationResponse) -> str:
    """将 DivinationResponse 渲染为完整 Markdown 文档。

    Args:
        response: 完整解卦响应

    Returns:
        Markdown 字符串
    """
    p = response.paipan
    gz = p.ganzhi
    md: list[str] = []

    # 标题
    md.append(f"# 解卦记录 `{response.divination_id}`")
    md.append("")

    # 起卦信息
    md.append("## 起卦信息")
    md.append("")
    md.append(f"- **所问事项**：{p.question}")
    md.append(f"- **起卦时间**：{p.qigua_time.strftime('%Y-%m-%d %H:%M')}")
    md.append("")

    # 时间地支与旬空
    md.append("## 时间地支与旬空")
    md.append("")
    md.append(
        f"- 年支：**{gz.get('year', '—')}**　月支：**{gz.get('month', '—')}**　"
        f"日支：**{gz.get('day', '—')}**　时支：**{gz.get('hour', '—')}**"
    )
    md.append(f"- 旬空：**{''.join(p.xunkong) if p.xunkong else '—'}空**")
    md.append("")

    # 本卦
    md.append("## 本卦")
    md.append("")
    md.extend(_format_hexagram_section(p.ben_gua))

    # 变卦
    if p.bian_gua:
        md.append("## 变卦")
        md.append("")
        md.extend(_format_hexagram_section(p.bian_gua))
    else:
        md.append("## 变卦")
        md.append("")
        md.append("_（无动爻，无变卦）_")
        md.append("")

    # 动爻汇总
    md.append("## 动爻汇总")
    md.append("")
    md.extend(_format_moving_lines(p.moving_positions))

    # 备注参考
    md.append("## 参考备忘")
    md.append("")
    md.append(_REFERENCE_NOTES)

    # 免责声明
    md.append("---")
    md.append("")
    md.append(f"> **{_DISCLAIMER}**")
    md.append("")

    return "\n".join(md)
