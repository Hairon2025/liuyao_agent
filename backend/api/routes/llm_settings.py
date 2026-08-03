"""注册用户的 LLM 连接设置。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.deps import (
    get_user_llm_settings_service,
    require_registered_user,
)
from backend.models.user import User
from backend.schema.api.llm_settings import (
    LLMConnectionTestResponse,
    UserLLMSettingsResponse,
    UserLLMSettingsUpsert,
)
from backend.services.exceptions import (
    UserLLMSettingsInvalidError,
    UserLLMSettingsRequiredError,
)
from backend.services.user_llm_settings import UserLLMSettingsService

router = APIRouter(prefix="/users/me/llm-settings", tags=["user-settings"])
RegisteredUserDep = Annotated[User, Depends(require_registered_user)]
SettingsServiceDep = Annotated[
    UserLLMSettingsService,
    Depends(get_user_llm_settings_service),
]


@router.get("", response_model=UserLLMSettingsResponse | None)
async def get_llm_settings(
    user: RegisteredUserDep,
    service: SettingsServiceDep,
):
    return await service.get(user.id)


@router.put("", response_model=UserLLMSettingsResponse)
async def upsert_llm_settings(
    payload: UserLLMSettingsUpsert,
    user: RegisteredUserDep,
    service: SettingsServiceDep,
):
    try:
        return await service.upsert(user.id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from None
    except UserLLMSettingsInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"服务端密钥配置不可用：{exc}",
        ) from None


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_settings(
    user: RegisteredUserDep,
    service: SettingsServiceDep,
) -> None:
    await service.delete(user.id)


@router.post("/test", response_model=LLMConnectionTestResponse)
async def test_llm_settings(
    user: RegisteredUserDep,
    service: SettingsServiceDep,
):
    try:
        return await service.test_connection(user.id)
    except UserLLMSettingsRequiredError:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="请先保存 LLM 设置",
        ) from None
    except UserLLMSettingsInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"服务端密钥配置不可用：{exc}",
        ) from None
