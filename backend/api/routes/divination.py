"""解卦相关路由。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.agent.liuyao_agent import analyst
from backend.api.deps import get_current_user, get_divination_service
from backend.models.user import User
from backend.schema.api.divination import (
    DivinationResponse,
    MarkdownResponse,
    QiguaRequest,
)
from backend.services.divination import DivinationService
from backend.services.exceptions import (
    DivinationNotFoundError,
    MarkdownNotFoundError,
)
from backend.utils.sse import text_stream_to_sse

router = APIRouter(prefix="/divinations", tags=["divination"])
CurrentUserDep = Annotated[User, Depends(get_current_user)]
DivinationServiceDep = Annotated[
    DivinationService,
    Depends(get_divination_service),
]


def _not_found(divination_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"解卦记录 {divination_id} 不存在",
    )


async def _get_interpretable_markdown(
    divination_id: str,
    user: User,
    service: DivinationService,
) -> str:
    """读取可供 Agent 解读的 Markdown，并统一处理前置错误。"""
    try:
        return await service.get_markdown(divination_id, user.id)
    except DivinationNotFoundError:
        raise _not_found(divination_id) from None
    except MarkdownNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"未找到 {divination_id} 的 Markdown，请先调用 "
            f"POST /divinations/{divination_id}/markdown 生成",
        ) from None


@router.post("", response_model=DivinationResponse)
async def create_divination(
    request: QiguaRequest,
    user: CurrentUserDep,
    service: DivinationServiceDep,
):
    """创建卦例，并将排盘、解读初始值和可选 Markdown 保存到数据库。"""
    try:
        return await service.create(request, user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from None


@router.get("", response_model=list[str])
async def list_divinations(
    user: CurrentUserDep,
    service: DivinationServiceDep,
):
    """按时间倒序列出当前用户的历史卦例 ID。"""
    return await service.list_ids(user.id)


@router.get("/{divination_id}", response_model=DivinationResponse)
async def get_divination(
    divination_id: str,
    user: CurrentUserDep,
    service: DivinationServiceDep,
):
    """读取当前用户的一条卦例。"""
    try:
        return await service.get(divination_id, user.id)
    except DivinationNotFoundError:
        raise _not_found(divination_id) from None


@router.delete("/{divination_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_divination(
    divination_id: str,
    user: CurrentUserDep,
    service: DivinationServiceDep,
) -> None:
    """删除当前用户的一条卦例。"""
    try:
        await service.delete(divination_id, user.id)
    except DivinationNotFoundError:
        raise _not_found(divination_id) from None


@router.post("/{divination_id}/markdown", response_model=MarkdownResponse)
async def generate_markdown(
    divination_id: str,
    user: CurrentUserDep,
    service: DivinationServiceDep,
):
    """生成格式化 Markdown 并保存到数据库。"""
    try:
        content = await service.generate_markdown(divination_id, user.id)
    except DivinationNotFoundError:
        raise _not_found(divination_id) from None
    return MarkdownResponse(
        divination_id=divination_id,
        content=content,
    )


@router.get("/{divination_id}/markdown", response_model=MarkdownResponse)
async def get_markdown(
    divination_id: str,
    user: CurrentUserDep,
    service: DivinationServiceDep,
):
    """读取数据库中已生成的 Markdown。"""
    try:
        content = await service.get_markdown(divination_id, user.id)
    except DivinationNotFoundError:
        raise _not_found(divination_id) from None
    except MarkdownNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Markdown 不存在，请先调用 "
            f"POST /divinations/{divination_id}/markdown 生成",
        ) from None
    return MarkdownResponse(
        divination_id=divination_id,
        content=content,
    )


@router.post(
    "/{divination_id}/interpret",
    response_model=DivinationResponse,
)
async def interpret_divination(
    divination_id: str,
    user: CurrentUserDep,
    service: DivinationServiceDep,
):
    """非流式调用 Agent 解卦，并将完整结果保存到数据库。"""
    markdown_content = await _get_interpretable_markdown(
        divination_id,
        user,
        service,
    )
    try:
        text = await analyst.interpret(markdown_content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解卦失败：{exc}",
        ) from None
    return await service.save_interpretation(
        divination_id,
        user.id,
        text,
    )


@router.post("/{divination_id}/interpret/stream")
async def interpret_divination_stream(
    divination_id: str,
    user: CurrentUserDep,
    service: DivinationServiceDep,
):
    """以 SSE 流式输出解卦文本，生成完成后将完整结果保存到数据库。"""
    markdown_content = await _get_interpretable_markdown(
        divination_id,
        user,
        service,
    )

    async def save_interpretation(full_content: str) -> None:
        await service.save_interpretation(
            divination_id,
            user.id,
            full_content,
        )

    return StreamingResponse(
        text_stream_to_sse(
            analyst.interpret_stream(markdown_content),
            on_complete=save_interpretation,
            error_prefix="解卦失败：",
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )
