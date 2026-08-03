"""FastAPI 请求级依赖注入。"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from backend.agent.chat_orchestrator import ChatAgentOrchestrator
from backend.agent.chatbot_agent import LiuYaoChatbot
from backend.agent.liuyao_agent import LiuYaoAnalyst
from backend.agent.memory.compactor import ChatMemoryCompactor
from backend.agent.memory_summary_agent import MemorySummaryAgent
from backend.agent.runtime.model import AgentModelFactory
from backend.agent.runtime.session import AgentSessionFactory
from backend.agent.suggested_question_agent import SuggestedQuestionAgent
from backend.config.settings import settings
from backend.db.session import get_db_session
from backend.models.user import User
from backend.repositories.agent_memory import AgentMemoryRepository
from backend.repositories.auth import AuthRepository
from backend.repositories.chat_message import ChatMessageRepository
from backend.repositories.chat_session import ChatSessionRepository
from backend.repositories.divination import DivinationRepository
from backend.repositories.llm_usage import LLMUsageRepository
from backend.repositories.user import UserRepository
from backend.repositories.user_llm_settings import UserLLMSettingsRepository
from backend.services.auth import AuthService
from backend.services.chat import ChatService
from backend.services.chat_divination_workflow import ChatDivinationWorkflow
from backend.services.divination import DivinationService
from backend.services.exceptions import (
    UserLLMSettingsInvalidError,
    UserLLMSettingsRequiredError,
)
from backend.services.llm_usage import LLMUsageRecorder
from backend.services.user import UserService
from backend.services.user_llm_settings import (
    ResolvedUserLLMConfig,
    UserLLMSettingsService,
)


def get_settings():
    return settings


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_user_service(session: DbSession) -> UserService:
    return UserService(
        repository=UserRepository(session),
        session=session,
    )


def get_auth_service(session: DbSession) -> AuthService:
    return AuthService(
        user_repository=UserRepository(session),
        auth_repository=AuthRepository(session),
        session=session,
        session_days=settings.auth_session_days,
    )


async def get_optional_current_user(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> User | None:
    return await service.authenticate(
        request.cookies.get(settings.auth_cookie_name)
    )


async def get_current_user(
    user: Annotated[User | None, Depends(get_optional_current_user)],
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态已失效，请重新登录",
        )
    return user


async def require_registered_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.user_type != "registered":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该功能需要先注册或登录账号",
        )
    return user


def get_user_llm_settings_service(
    session: DbSession,
) -> UserLLMSettingsService:
    return UserLLMSettingsService(
        repository=UserLLMSettingsRepository(session),
        session=session,
        encryption_key=settings.user_llm_encryption_key,
        allow_private_base_urls=settings.allow_private_llm_base_urls,
    )


async def get_resolved_user_llm_config(
    user: Annotated[User, Depends(require_registered_user)],
    service: Annotated[
        UserLLMSettingsService,
        Depends(get_user_llm_settings_service),
    ],
) -> ResolvedUserLLMConfig:
    try:
        return await service.resolve(user.id)
    except UserLLMSettingsRequiredError:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="请先在用户设置中配置 LLM API Key、Base URL 和模型",
        ) from None
    except UserLLMSettingsInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"用户 LLM 配置不可用：{exc}",
        ) from None


def get_divination_service(session: DbSession) -> DivinationService:
    return DivinationService(
        repository=DivinationRepository(session),
        session=session,
    )


def _model_factory(
    config: ResolvedUserLLMConfig,
    model: str,
) -> AgentModelFactory:
    return AgentModelFactory(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout_seconds=config.timeout_seconds,
        default_model=model,
    )


def _usage_recorder(user: User, session: AsyncSession) -> LLMUsageRecorder:
    return LLMUsageRecorder(
        user_id=user.id,
        repository=LLMUsageRepository(session),
        session=session,
    )


def get_user_analyst(
    session: DbSession,
    user: Annotated[User, Depends(require_registered_user)],
    config: Annotated[
        ResolvedUserLLMConfig,
        Depends(get_resolved_user_llm_config),
    ],
) -> LiuYaoAnalyst:
    return LiuYaoAnalyst(
        model_factory=_model_factory(config, config.analyst_model),
        usage_recorder=_usage_recorder(user, session),
    )


def get_chat_service(
    session: DbSession,
    user: Annotated[User, Depends(require_registered_user)],
    config: Annotated[
        ResolvedUserLLMConfig,
        Depends(get_resolved_user_llm_config),
    ],
) -> ChatService:
    """为当前用户的密钥创建一次请求级多 Agent 执行链。"""
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

    usage = _usage_recorder(user, session)
    analyst = LiuYaoAnalyst(
        model_factory=_model_factory(config, config.analyst_model),
        usage_recorder=usage,
    )
    suggested = SuggestedQuestionAgent(
        model_factory=_model_factory(config, config.suggestion_model),
        usage_recorder=usage,
    )
    memory_summary = MemorySummaryAgent(
        model_factory=_model_factory(config, config.memory_model),
        usage_recorder=usage,
    )
    memory_compactor = ChatMemoryCompactor(
        session_repository=session_repository,
        memory_repository=AgentMemoryRepository(session),
        summary_agent=memory_summary,
        session=session,
        trigger_items=settings.memory_summary_trigger_items,
        keep_recent_items=settings.memory_summary_keep_recent_items,
        input_max_chars=settings.memory_summary_input_max_chars,
        context_recent_limit=settings.chat_context_recent_limit,
    )
    coordinator = LiuYaoChatbot(
        model_factory=_model_factory(config, config.model),
        max_turns=settings.chat_max_steps,
        usage_recorder=usage,
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
        agent_session_factory=AgentSessionFactory(
            engine=sdk_engine,
            recent_limit=settings.chat_context_recent_limit,
            memory_enabled=True,
        ),
        divination_service=divination_service,
        chat_divination_workflow=workflow,
        session=session,
        suggested_question_agent=suggested,
        memory_compactor=memory_compactor,
    )
