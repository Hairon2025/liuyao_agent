"""Server-Sent Events (SSE) helpers.

负责把异步文本流编码成 SSE，并在流正常结束后执行可选的持久化回调。
Agent 只需产出文本片段，不需要了解 HTTP 协议或结束标记。
"""
from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable

SSE_DONE = "[DONE]"
SSE_ERROR_PREFIX = "[ERROR]"

OnComplete = Callable[[str], Awaitable[None]]


def encode_sse(data: str) -> str:
    """把任意文本编码为一个默认类型的 SSE message。

    每一行都需要独立的 ``data:`` 前缀；使用 ``split("\\n")`` 保留末尾
    换行，避免 Markdown 文本块在浏览器端被截断或粘连。
    """
    normalized = data.replace("\r\n", "\n").replace("\r", "\n")
    data_lines = "".join(f"data: {line}\n" for line in normalized.split("\n"))
    return f"{data_lines}\n"


async def text_stream_to_sse(
    chunks: AsyncIterable[str],
    *,
    on_complete: OnComplete | None = None,
    error_prefix: str = "",
) -> AsyncIterator[str]:
    """将文本异步迭代器转换为 SSE 消息流。

    - 普通文本片段按原样编码；
    - 正常结束后调用 ``on_complete``，再发送 ``[DONE]``；
    - 生成或持久化失败时发送 ``[ERROR]...``，且不发送 ``[DONE]``。

    该函数不捕获任务取消异常，因此客户端断开连接时，上游生成器可以正常
    收到取消信号。
    """
    full_content: list[str] = []
    try:
        async for chunk in chunks:
            if not chunk:
                continue
            full_content.append(chunk)
            yield encode_sse(chunk)

        if on_complete is not None:
            await on_complete("".join(full_content))
    except Exception as exc:
        yield encode_sse(f"{SSE_ERROR_PREFIX}{error_prefix}{exc}")
        return

    yield encode_sse(SSE_DONE)
