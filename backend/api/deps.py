"""FastAPI 依赖注入"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.settings import settings
from backend.db.session import get_db_session
from backend.repositories.user import UserRepository
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
