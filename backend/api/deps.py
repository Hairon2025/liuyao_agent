"""FastAPI 依赖注入"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.settings import settings
from backend.agent.context_builder import ChatContextBuilder
from backend.agent.context_summarizer import ChatContextSummarizer
from backend.agent.model import OpenAIChatModelAdapter
from backend.agent.react_runner import ReActRunner
from backend.agent.tools import (
    CreateDivinationTool,
    GetDivinationTool,
    ListDivinationsTool,
    ToolRegistry,
)
from backend.db.session import get_db_session
from backend.models.user import User
from backend.repositories.divination import DivinationRepository
from backend.repositories.chat_message import ChatMessageRepository
from backend.repositories.chat_session import ChatSessionRepository
from backend.repositories.user import UserRepository
from backend.services.divination import DivinationService
from backend.services.chat import ChatService
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


def get_chat_service(session: DbSession) -> ChatService:
    """组装一次请求使用的 Chatbot 执行链。"""
    session_repository = ChatSessionRepository(session)
    message_repository = ChatMessageRepository(session)
    divination_repository = DivinationRepository(session)
    divination_service = DivinationService(
        repository=divination_repository,
        session=session,
    )
    model_adapter = OpenAIChatModelAdapter()
    registry = ToolRegistry(
        [
            CreateDivinationTool(divination_service),
            GetDivinationTool(divination_service),
            ListDivinationsTool(divination_service),
        ]
    )
    prompt_path = (
        Path(__file__).resolve().parents[1]
        / "agent"
        / "prompt"
        / "chatbot.txt"
    )
    runner = ReActRunner(
        model_adapter=model_adapter,
        tool_registry=registry,
        instructions=prompt_path.read_text(encoding="utf-8"),
        max_steps=settings.chat_max_steps,
    )
    context_builder = ChatContextBuilder(
        session_repository=session_repository,
        message_repository=message_repository,
        recent_message_limit=settings.chat_context_recent_limit,
    )
    summarizer = ChatContextSummarizer(
        session_repository=session_repository,
        message_repository=message_repository,
        model_adapter=model_adapter,
        trigger_messages=settings.chat_summary_trigger_messages,
        keep_recent=settings.chat_summary_keep_recent,
    )
    return ChatService(
        session_repository=session_repository,
        message_repository=message_repository,
        divination_repository=divination_repository,
        context_builder=context_builder,
        runner=runner,
        summarizer=summarizer,
        session=session,
    )
