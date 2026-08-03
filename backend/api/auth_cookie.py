"""认证 Cookie 的统一写入与删除。"""
from fastapi import Response

from backend.config.settings import settings
from backend.services.auth import AuthResult


def set_auth_cookie(response: Response, result: AuthResult) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=result.session_token,
        max_age=result.max_age_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )
