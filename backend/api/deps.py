"""FastAPI 依赖注入"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.settings import settings
from backend.db.session import get_db_session
from backend.models.user import User
from backend.repositories.divination import DivinationRepository
from backend.repositories.user import UserRepository
from backend.services.divination import DivinationService
from backend.services.user import UserService


def get_settings():
    return settings


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_user_service(session: DbSession) -> UserService:
    """组装 UserService 及其 Repository。"""
    return UserService(
        repository=UserRepository(session),
        session=session,
    )


async def get_current_user(
    session: DbSession,
    x_user_id: Annotated[
        str | None,
        Header(alias="X-User-ID"),
    ] = None,
) -> User:
    """读取 MVP 阶段的客户端身份。

    `X-User-ID` 只是接入正式认证前的临时身份传输方式，不应视为安全登录态。
    """
    if x_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 X-User-ID 请求头",
        )
    try:
        user_id = uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-ID 格式无效",
        ) from None

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="当前用户不存在",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前用户已停用",
        )
    return user


def get_divination_service(session: DbSession) -> DivinationService:
    """组装 DivinationService 及其 Repository。"""
    return DivinationService(
        repository=DivinationRepository(session),
        session=session,
    )
