"""用户相关路由。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import get_user_service
from backend.schema.api.user import UserCreate, UserResponse, UserUpdate
from backend.services.exceptions import UserNotFoundError
from backend.services.user import UserService

router = APIRouter(prefix="/users", tags=["user"])
UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def _user_not_found(user_id: uuid.UUID) -> HTTPException:
    """统一生成用户不存在的 HTTP 异常。"""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"用户 {user_id} 不存在",
    )


@router.post(
    "/guests",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_guest_user(
    payload: UserCreate,
    service: UserServiceDep,
):
    """创建最小匿名用户，用户 ID 由服务端生成。"""
    return await service.create_guest(display_name=payload.display_name)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    service: UserServiceDep,
):
    """按 ID 获取用户。

    当前仅提供基础数据能力；接入身份认证后应改为从登录态校验所有权。
    """
    try:
        return await service.get_user(user_id)
    except UserNotFoundError:
        raise _user_not_found(user_id) from None


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    service: UserServiceDep,
):
    """更新用户资料，目前仅支持修改或清空昵称。"""
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少提供一个需要修改的字段",
        )

    try:
        return await service.update_profile(user_id, changes)
    except UserNotFoundError:
        raise _user_not_found(user_id) from None
