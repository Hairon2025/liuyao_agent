"""Service 层业务异常。

这些异常不依赖 FastAPI，由 API 层统一转换为 HTTP 状态码。
"""


class UserNotFoundError(Exception):
    """目标用户不存在。"""


class DivinationNotFoundError(Exception):
    """当前用户下不存在目标卦例。"""


class MarkdownNotFoundError(Exception):
    """目标卦例尚未生成排盘 Markdown。"""


class ChatSessionNotFoundError(Exception):
    """当前用户下不存在目标聊天会话。"""


class ChatSessionArchivedError(Exception):
    """归档会话不能继续发送消息。"""


class ChatDivinationOwnershipError(Exception):
    """准备关联的卦例不存在或不属于当前用户。"""
