"""为低成本追问模型裁剪最新一轮对话上下文。"""
from __future__ import annotations

import re

DISCLAIMER = "本结果仅供文化娱乐参考，不构成任何人生决策依据"
_BLOCK_SEPARATOR = re.compile(r"\n\s*\n")


def build_suggestion_context(
    *,
    user_message: str,
    assistant_answer: str,
    answer_max_chars: int,
    user_max_chars: int,
) -> tuple[str, str]:
    """保留用户问题、回答开头和末尾有效段落，过滤固定免责声明。

    完整解读通常较长，而结尾常是免责声明。仅截取字符串末尾会把真正的分析
    挤掉，因此这里保留少量开头用于识别主题，再从末尾反向选择有效段落。
    """
    if answer_max_chars < 1 or user_max_chars < 1:
        raise ValueError("追问上下文长度必须大于等于 1")

    compact_user = user_message.strip()[:user_max_chars]
    normalized_answer = assistant_answer.replace("\r\n", "\n").replace(
        "\r",
        "\n",
    )
    blocks = [
        block.strip()
        for block in _BLOCK_SEPARATOR.split(normalized_answer)
        if block.strip() and DISCLAIMER not in block
    ]
    cleaned_answer = "\n\n".join(blocks)
    if len(cleaned_answer) <= answer_max_chars:
        return compact_user, cleaned_answer

    opening_limit = min(240, max(1, answer_max_chars // 4))
    opening = blocks[0][:opening_limit] if blocks else ""
    remaining = max(0, answer_max_chars - len(opening) - 2)

    tail_blocks: list[str] = []
    used = 0
    for block in reversed(blocks[1:]):
        separator = 2 if tail_blocks else 0
        available = remaining - used - separator
        if available <= 0:
            break
        selected = block[-available:]
        tail_blocks.append(selected)
        used += len(selected) + separator
        if len(selected) < len(block):
            break

    tail = "\n\n".join(reversed(tail_blocks))
    compact_answer = (
        f"{opening}\n\n{tail}" if opening and tail else opening or tail
    )
    return compact_user, compact_answer[:answer_max_chars]
