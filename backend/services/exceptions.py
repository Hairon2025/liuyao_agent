"""Service 层业务异常。

这些异常不依赖 FastAPI，由 API 层统一转换为 HTTP 状态码。
"""


class UserNotFoundError(Exception):
    """目标用户不存在。"""
