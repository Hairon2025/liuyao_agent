"""游客 Session、注册、登录、注销和当前身份。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from backend.api.auth_cookie import clear_auth_cookie, set_auth_cookie
from backend.api.deps import (
    get_auth_service,
    get_current_user,
    get_optional_current_user,
)
from backend.config.settings import settings
from backend.models.user import User
from backend.schema.api.auth import (
    AuthResponse,
    GuestSessionCreate,
    LoginRequest,
    RegisterRequest,
)
from backend.schema.api.user import UserResponse
from backend.services.auth import AuthService
from backend.services.exceptions import (
    InvalidCredentialsError,
    UsernameAlreadyExistsError,
)
from fastapi import HTTPException

router = APIRouter(prefix="/auth", tags=["auth"])
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
OptionalUserDep = Annotated[User | None, Depends(get_optional_current_user)]


@router.post(
    "/guests",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_guest_session(
    payload: GuestSessionCreate,
    response: Response,
    current_user: OptionalUserDep,
    service: AuthServiceDep,
) -> AuthResponse:
    if current_user is not None:
        return AuthResponse(user=UserResponse.model_validate(current_user))
    result = await service.create_guest(payload.display_name)
    set_auth_cookie(response, result)
    return AuthResponse(user=UserResponse.model_validate(result.user))


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    current_user: OptionalUserDep,
    service: AuthServiceDep,
) -> AuthResponse:
    try:
        result = await service.register(
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
            current_user=current_user,
            current_token=request.cookies.get(settings.auth_cookie_name),
        )
    except UsernameAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        ) from None
    set_auth_cookie(response, result)
    return AuthResponse(user=UserResponse.model_validate(result.user))


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: AuthServiceDep,
) -> AuthResponse:
    try:
        result = await service.login(
            payload.username,
            payload.password,
            request.cookies.get(settings.auth_cookie_name),
        )
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        ) from None
    set_auth_cookie(response, result)
    return AuthResponse(user=UserResponse.model_validate(result.user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    service: AuthServiceDep,
) -> None:
    await service.logout(request.cookies.get(settings.auth_cookie_name))
    clear_auth_cookie(response)


@router.get("/me", response_model=AuthResponse)
async def get_me(user: CurrentUserDep) -> AuthResponse:
    return AuthResponse(user=UserResponse.model_validate(user))
