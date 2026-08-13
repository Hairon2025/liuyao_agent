"""游客 Session、注册、登录和注销业务。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.auth import AuthSession, UserCredential
from backend.models.user import User, utc_now
from backend.repositories.auth import AuthRepository
from backend.repositories.user import UserRepository
from backend.services.exceptions import (
    InvalidCredentialsError,
    UsernameAlreadyExistsError,
)
from backend.utils.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    normalize_username,
    verify_password,
)


@dataclass(frozen=True)
class AuthResult:
    user: User
    session_token: str
    max_age_seconds: int


class AuthService:
    def __init__(
        self,
        *,
        user_repository: UserRepository,
        auth_repository: AuthRepository,
        session: AsyncSession,
        session_days: int,
    ):
        self._users = user_repository
        self._auth = auth_repository
        self._session = session
        self._session_days = session_days

    async def create_guest(
        self,
        display_name: str | None = None,
    ) -> AuthResult:
        user = User(
            user_type="guest",
            display_name=display_name,
            is_active=True,
        )
        await self._users.add(user)
        result = await self._issue_session(user)
        await self._session.commit()
        await self._session.refresh(user)
        return result

    async def register(
        self,
        *,
        username: str,
        password: str,
        display_name: str | None,
        current_user: User | None,
        current_token: str | None,
    ) -> AuthResult:
        normalized = normalize_username(username)
        if await self._users.get_by_normalized_username(normalized):
            raise UsernameAlreadyExistsError(username)

        if current_user is not None and current_user.user_type == "guest":
            user = current_user
            await self._users.update(
                user,
                {
                    "user_type": "registered",
                    "username": username.strip(),
                    "username_normalized": normalized,
                    "display_name": display_name or user.display_name,
                    "last_login_at": utc_now(),
                },
            )
        else:
            user = User(
                user_type="registered",
                username=username.strip(),
                username_normalized=normalized,
                display_name=display_name,
                is_active=True,
                last_login_at=utc_now(),
            )
            await self._users.add(user)

        await self._auth.add_credential(
            UserCredential(
                user_id=user.id,
                password_hash=hash_password(password),
            )
        )
        if current_token:
            await self._auth.revoke(
                hash_session_token(current_token),
                utc_now(),
            )
        result = await self._issue_session(user)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            raise UsernameAlreadyExistsError(username) from None
        await self._session.refresh(user)
        return result

    async def login(
        self,
        username: str,
        password: str,
        current_user: User | None = None,
        current_token: str | None = None,
    ) -> AuthResult:
        user = await self._auth.get_user_with_credential(
            normalize_username(username)
        )
        if (
            user is None
            or user.credential is None
            or not user.is_active
            or not verify_password(user.credential.password_hash, password)
        ):
            raise InvalidCredentialsError()

        await self._users.update(user, {"last_login_at": utc_now()})
        if current_token:
            await self._auth.revoke(
                hash_session_token(current_token),
                utc_now(),
            )

        # 游客登录已有账号时，把当前游客 Cookie 下产生的卦例等数据归并到
        # 目标账号。注册用户之间切换账号绝不能转移数据，避免越权合并。
        if (
            current_user is not None
            and current_user.user_type == "guest"
            and current_user.id != user.id
        ):
            await self._users.reassign_owned_resources(
                current_user.id,
                user.id,
            )
            await self._users.delete_guest(current_user.id)

        result = await self._issue_session(user)
        await self._session.commit()
        await self._session.refresh(user)
        return result

    async def authenticate(self, token: str | None) -> User | None:
        if not token:
            return None
        auth_session = await self._auth.get_active_session(
            hash_session_token(token),
            utc_now(),
        )
        if auth_session is None or not auth_session.user.is_active:
            return None
        return auth_session.user

    async def logout(self, token: str | None) -> None:
        if token:
            await self._auth.revoke(hash_session_token(token), utc_now())
            await self._session.commit()

    async def _issue_session(self, user: User) -> AuthResult:
        token = generate_session_token()
        max_age = self._session_days * 24 * 60 * 60
        now = utc_now()
        await self._auth.add_session(
            AuthSession(
                user_id=user.id,
                token_hash=hash_session_token(token),
                expires_at=now + timedelta(seconds=max_age),
                last_seen_at=now,
            )
        )
        return AuthResult(
            user=user,
            session_token=token,
            max_age_seconds=max_age,
        )
