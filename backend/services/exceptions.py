"""Service 层业务异常。

这些异常不依赖 FastAPI，由 API 层统一转换为 HTTP 状态码。
"""


class UserNotFoundError(Exception):
    """目标用户不存在。"""


class DivinationNotFoundError(Exception):
    """当前用户下不存在目标卦例。"""


class MarkdownNotFoundError(Exception):
    """目标卦例尚未生成排盘 Markdown。"""
