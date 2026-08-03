"""当前登录用户资料；身份由 HttpOnly Session Cookie 决定。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from backend.api.auth_cookie import set_auth_cookie
from backend.api.deps import (
    get_auth_service,
    get_current_user,
    get_optional_current_user,
    get_user_service,
)
from backend.models.user import User
from backend.schema.api.auth import GuestSessionCreate
from backend.schema.api.user import UserResponse, UserUpdate
from backend.services.auth import AuthService
from backend.services.user import UserService

router = APIRouter(prefix="/users", tags=["user"])
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
OptionalUserDep = Annotated[User | None, Depends(get_optional_current_user)]


@router.post(
    "/guests",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    deprecated=True,
)
async def create_guest_user_compat(
    payload: GuestSessionCreate,
    response: Response,
    current_user: OptionalUserDep,
    service: AuthServiceDep,
):
    """兼容旧客户端；新客户端使用 POST /auth/guests。"""
    if current_user is not None:
        return UserResponse.model_validate(current_user)
    result = await service.create_guest(payload.display_name)
    set_auth_cookie(response, result)
    return UserResponse.model_validate(result.user)


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUserDep):
    return user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdate,
    user: CurrentUserDep,
    service: UserServiceDep,
):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少提供一个需要修改的字段",
        )
    return await service.update_profile(user.id, changes)
