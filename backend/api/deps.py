"""FastAPI 依赖注入"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from backend.config.settings import settings
from backend.agent.chatbot_agent import LiuYaoChatbot
from backend.agent.chat_orchestrator import ChatAgentOrchestrator
from backend.agent.liuyao_agent import analyst
from backend.agent.runtime.model import AgentModelFactory
from backend.agent.runtime.session import AgentSessionFactory
from backend.agent.suggested_question_agent import suggested_question_agent
from backend.db.session import get_db_session
from backend.models.user import User
from backend.repositories.chat_message import ChatMessageRepository
from backend.repositories.chat_session import ChatSessionRepository
from backend.repositories.divination import DivinationRepository
from backend.repositories.user import UserRepository
from backend.services.chat import ChatService
from backend.services.chat_divination_workflow import ChatDivinationWorkflow
from backend.services.divination import DivinationService
from backend.services.user import UserService


_agent_model_factory = AgentModelFactory()


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
    """组装一次请求使用的 Agents SDK Chatbot 执行链。"""
    session_repository = ChatSessionRepository(session)
    message_repository = ChatMessageRepository(session)
    divination_repository = DivinationRepository(session)
    divination_service = DivinationService(
        repository=divination_repository,
        session=session,
    )
    workflow = ChatDivinationWorkflow(
        chat_session_repository=session_repository,
        divination_service=divination_service,
        session=session,
    )
    bind = session.bind
    if isinstance(bind, AsyncEngine):
        sdk_engine = bind
    elif isinstance(bind, AsyncConnection):
        sdk_engine = bind.engine
    else:
        raise RuntimeError("ChatService 需要绑定 AsyncEngine 的数据库会话")

    agent_session_factory = AgentSessionFactory(
        engine=sdk_engine,
        recent_limit=settings.chat_context_recent_limit,
    )
    coordinator = LiuYaoChatbot(
        model_factory=_agent_model_factory,
        max_turns=settings.chat_max_steps,
    )
    chatbot = ChatAgentOrchestrator(
        coordinator=coordinator,
        analyst=analyst,
        divination_service=divination_service,
    )
    return ChatService(
        session_repository=session_repository,
        message_repository=message_repository,
        divination_repository=divination_repository,
        chatbot=chatbot,
        agent_session_factory=agent_session_factory,
        divination_service=divination_service,
        chat_divination_workflow=workflow,
        session=session,
        suggested_question_agent=suggested_question_agent,
    )
