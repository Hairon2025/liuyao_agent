"""Service 层业务异常。

这些异常不依赖 FastAPI，由 API 层统一转换为 HTTP 状态码。
"""


class UserNotFoundError(Exception):
    """目标用户不存在。"""


class UsernameAlreadyExistsError(Exception):
    """注册用户名已存在。"""


class InvalidCredentialsError(Exception):
    """用户名或密码错误。"""


class RegisteredUserRequiredError(Exception):
    """当前功能只允许注册用户使用。"""


class UserLLMSettingsRequiredError(Exception):
    """用户尚未配置自己的模型连接。"""


class UserLLMSettingsInvalidError(Exception):
    """用户模型配置无法解密或不合法。"""


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


class ChatMessageNotFoundError(Exception):
    """当前用户或会话下不存在目标消息。"""


class ChatSuggestionSourceError(Exception):
    """目标消息不能作为追问建议的来源。"""


class ChatSuggestionGenerationError(Exception):
    """追问建议模型调用或结果保存失败。"""
