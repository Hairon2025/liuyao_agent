"""Chatbot 会话与流式消息路由。"""
from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from backend.api.deps import get_chat_service, get_current_user
from backend.models.user import User
from backend.schema.api.chat import (
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionResponse,
    ChatSessionUpdate,
    ChatTurnRequest,
)
from backend.services.chat import ChatService
from backend.services.exceptions import (
    ChatDivinationOwnershipError,
    ChatSessionArchivedError,
    ChatSessionNotFoundError,
)
from backend.utils.sse import chat_events_to_sse

router = APIRouter(prefix="/chat/sessions", tags=["chat"])
CurrentUserDep = Annotated[User, Depends(get_current_user)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


def _session_not_found(session_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"聊天会话 {session_id} 不存在",
    )


def _archived_session(session_id: uuid.UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"聊天会话 {session_id} 已归档，不能继续发送消息",
    )


@router.post(
    "",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_session(
    payload: ChatSessionCreate,
    user: CurrentUserDep,
    service: ChatServiceDep,
):
    """创建属于当前用户的聊天会话。"""
    try:
        return await service.create_session(payload, user.id)
    except ChatDivinationOwnershipError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="需要关联的卦例不存在",
        ) from None


@router.get("", response_model=list[ChatSessionResponse])
async def list_chat_sessions(
    user: CurrentUserDep,
    service: ChatServiceDep,
    session_status: Annotated[
        Literal["active", "archived"] | None,
        Query(alias="status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """分页列出当前用户的聊天会话。"""
    return await service.list_sessions(
        user.id,
        status=session_status,
        limit=limit,
        offset=offset,
    )


@router.get("/{session_id}", response_model=ChatSessionResponse)
async def get_chat_session(
    session_id: uuid.UUID,
    user: CurrentUserDep,
    service: ChatServiceDep,
):
    """读取一条当前用户拥有的会话。"""
    try:
        return await service.get_session(session_id, user.id)
    except ChatSessionNotFoundError:
        raise _session_not_found(session_id) from None


@router.patch("/{session_id}", response_model=ChatSessionResponse)
async def update_chat_session(
    session_id: uuid.UUID,
    payload: ChatSessionUpdate,
    user: CurrentUserDep,
    service: ChatServiceDep,
):
    """修改标题、归档状态、当前卦例或会话模型。"""
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少提供一个需要修改的字段",
        )
    try:
        return await service.update_session(
            session_id,
            user.id,
            values,
        )
    except ChatSessionNotFoundError:
        raise _session_not_found(session_id) from None
    except ChatDivinationOwnershipError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="需要关联的卦例不存在",
        ) from None


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chat_session(
    session_id: uuid.UUID,
    user: CurrentUserDep,
    service: ChatServiceDep,
) -> None:
    """删除会话，数据库会级联删除其消息。"""
    try:
        await service.delete_session(session_id, user.id)
    except ChatSessionNotFoundError:
        raise _session_not_found(session_id) from None


@router.get(
    "/{session_id}/messages",
    response_model=list[ChatMessageResponse],
)
async def list_chat_messages(
    session_id: uuid.UUID,
    user: CurrentUserDep,
    service: ChatServiceDep,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    recent: bool = False,
):
    """使用消息序号游标读取会话历史。"""
    if recent and after_sequence:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="recent=true 时不能同时提供 after_sequence",
        )
    try:
        return await service.list_messages(
            session_id,
            user.id,
            after_sequence=after_sequence,
            limit=limit,
            recent=recent,
        )
    except ChatSessionNotFoundError:
        raise _session_not_found(session_id) from None


@router.post("/{session_id}/messages/stream")
async def stream_chat_message(
    session_id: uuid.UUID,
    payload: ChatTurnRequest,
    user: CurrentUserDep,
    service: ChatServiceDep,
):
    """通过命名 SSE 执行一轮 ReAct 对话。"""
    try:
        await service.ensure_can_chat(session_id, user.id)
    except ChatSessionNotFoundError:
        raise _session_not_found(session_id) from None
    except ChatSessionArchivedError:
        raise _archived_session(session_id) from None

    return StreamingResponse(
        chat_events_to_sse(
            service.stream_reply(
                session_id=session_id,
                user_id=user.id,
                user_message=payload.message,
                model=payload.model,
            )
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )
