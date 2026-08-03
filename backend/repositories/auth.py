"""用户凭证与登录 Session 数据访问。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from backend.models.auth import AuthSession, UserCredential
from backend.models.user import User


class AuthRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add_credential(
        self,
        credential: UserCredential,
    ) -> UserCredential:
        self._session.add(credential)
        await self._session.flush()
        return credential

    async def get_user_with_credential(
        self,
        normalized_username: str,
    ) -> User | None:
        return await self._session.scalar(
            select(User)
            .options(joinedload(User.credential))
            .where(User.username_normalized == normalized_username)
        )

    async def add_session(self, auth_session: AuthSession) -> AuthSession:
        self._session.add(auth_session)
        await self._session.flush()
        return auth_session

    async def get_active_session(
        self,
        token_hash: str,
        now: datetime,
    ) -> AuthSession | None:
        return await self._session.scalar(
            select(AuthSession)
            .options(joinedload(AuthSession.user))
            .where(
                AuthSession.token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )

    async def revoke(self, token_hash: str, revoked_at: datetime) -> bool:
        result = await self._session.execute(
            update(AuthSession)
            .where(
                AuthSession.token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        return result.rowcount == 1
