"""ChatService 与 Agents SDK 运行时边界的集成测试。"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.agent.runtime.session import AgentSessionFactory
from backend.db.base import Base
from backend.db.session import enable_sqlite_foreign_keys
from backend.models.divination import Divination
from backend.models.user import User
from backend.repositories.chat_message import ChatMessageRepository
from backend.repositories.chat_session import ChatSessionRepository
from backend.repositories.divination import DivinationRepository
from backend.schema.agent import (
    ChatEvent,
    ChatEventType,
    SuggestedQuestions,
    ToolResult,
)
from backend.schema.api.chat import ChatSessionCreate
from backend.schema.api.divination import QiguaMethod
from backend.services.chat import ChatService
from backend.services.chat_divination_workflow import ChatDivinationWorkflow
from backend.services.divination import DivinationService
from backend.services.chat_run_registry import ChatRunRegistry


class FakeRuntime:
    """模拟 SDK Runtime；Service 测试不访问真实模型。"""

    def __init__(self, divination_id: str):
        self.divination_id = divination_id
        self.calls = []

    async def stream(self, **kwargs):
        self.calls.append(kwargs)
        yield ChatEvent(
            event_type=ChatEventType.TOOL_CALL_STARTED,
            tool_call_id="call-1",
            tool_name="get_divination",
            tool_arguments={"divination_id": self.divination_id},
        )
        yield ChatEvent(
            event_type=ChatEventType.TOOL_CALL_COMPLETED,
            tool_call_id="call-1",
            tool_name="get_divination",
            tool_result=ToolResult(
                success=True,
                model_content="真实排盘",
                data={"divination_id": self.divination_id},
            ),
        )
        yield ChatEvent(
            event_type=ChatEventType.TEXT_DELTA,
            content="整体平稳。",
        )
        yield ChatEvent(
            event_type=ChatEventType.MESSAGE_COMPLETED,
            content="整体平稳。",
        )


class BackgroundToolRuntime:
    """模拟 SDK：先发送开始事件，再在后台执行共享 Session 的业务工具。"""

    def __init__(self):
        self.release_tool = asyncio.Event()
        self.tool_task: asyncio.Task | None = None

    async def stream(self, **kwargs):
        context = kwargs["context"]

        async def run_tool():
            await self.release_tool.wait()
            return await context.chat_divination_workflow.process(
                user_id=context.user_id,
                session_id=context.session_id,
                method=QiguaMethod.RANDOM,
                question="工作机会",
            )

        self.tool_task = asyncio.create_task(run_tool())
        yield ChatEvent(
            event_type=ChatEventType.TOOL_CALL_STARTED,
            tool_call_id="background-call",
            tool_name="process_divination_request",
            tool_arguments={
                "method": "random",
                "question": "工作机会",
            },
        )

        self.release_tool.set()
        outcome = await self.tool_task
        yield ChatEvent(
            event_type=ChatEventType.TOOL_CALL_COMPLETED,
            tool_call_id="background-call",
            tool_name="process_divination_request",
            tool_result=ToolResult(
                success=True,
                model_content="已完成排盘",
                data={"divination_id": outcome.divination_id},
            ),
        )
        yield ChatEvent(
            event_type=ChatEventType.MESSAGE_COMPLETED,
            content="已经完成随机起卦。",
        )


class FakeSuggestedQuestionAgent:
    def __init__(self):
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        assert kwargs["user_message"] == "请继续分析"
        assert kwargs["assistant_answer"] == "整体平稳。"
        return SuggestedQuestions(
            questions=["用神旺衰怎么看？", "动爻有什么影响？", "应期如何判断？"]
        )


class CancellableRuntime:
    """写入一条模拟 SDK Item 后等待，用于验证显式取消与上下文回滚。"""

    def __init__(self):
        self.started = asyncio.Event()

    async def stream(self, **kwargs):
        await kwargs["session"].add_items(
            [{"role": "user", "content": "本轮不完整输入"}]
        )
        self.started.set()
        await asyncio.Event().wait()
        if False:  # pragma: no cover - 保持异步生成器类型
            yield ChatEvent(
                event_type=ChatEventType.MESSAGE_COMPLETED,
                content="不会生成",
            )


@pytest.mark.asyncio
async def test_chat_service_persists_sdk_runtime_events(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'chat-service.db').as_posix()}",
        poolclass=NullPool,
    )
    enable_sqlite_foreign_keys(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as session:
        user = User()
        divination = Divination(
            id="d" * 32,
            user=user,
            method="random",
            question="工作如何",
            qigua_time=datetime.now(timezone.utc),
            paipan={"ben_gua": {"name": "乾为天"}},
        )
        session.add_all([user, divination])
        await session.commit()
        user_id = user.id
        divination_id = divination.id

    async with factory() as session:
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
        runtime = FakeRuntime(divination_id)
        agent_sessions = AgentSessionFactory(engine=engine, recent_limit=10)
        suggestion_agent = FakeSuggestedQuestionAgent()
        service = ChatService(
            session_repository=session_repository,
            message_repository=message_repository,
            divination_repository=divination_repository,
            chatbot=runtime,  # type: ignore[arg-type]
            agent_session_factory=agent_sessions,
            divination_service=divination_service,
            chat_divination_workflow=workflow,
            session=session,
            suggested_question_agent=suggestion_agent,
        )
        created = await service.create_session(ChatSessionCreate(), user_id)

        events = [
            event
            async for event in service.stream_reply(
                session_id=created.id,
                user_id=user_id,
                user_message="  请继续分析  ",
            )
        ]
        messages = await service.list_messages(created.id, user_id)
        updated = await service.get_session(created.id, user_id)

        assert events[-1].event_type == ChatEventType.MESSAGE_COMPLETED
        assert events[-1].message_id == messages[-1].id
        assert runtime.calls[0]["user_message"] == "请继续分析"
        assert runtime.calls[0]["context"].user_id == user_id
        assert str(runtime.calls[0]["session"].session_id) == str(created.id)
        assert [message.sequence for message in messages] == [1, 2, 3, 4]
        assert [
            (message.role, message.message_type)
            for message in messages
        ] == [
            ("user", "text"),
            ("assistant", "tool_call"),
            ("tool", "tool_result"),
            ("assistant", "text"),
        ]
        assert messages[-1].content == "整体平稳。"
        assert updated.active_divination_id == divination_id
        assert updated.title == "请继续分析"
        assistant_message_id = messages[-1].id

        generated = await service.generate_suggestions(
            session_id=created.id,
            user_id=user_id,
            assistant_message_id=assistant_message_id,
        )
        cached = await service.generate_suggestions(
            session_id=created.id,
            user_id=user_id,
            assistant_message_id=assistant_message_id,
        )
        messages = await service.list_messages(created.id, user_id)

        assert generated.cached is False
        assert cached.cached is True
        assert generated.questions == cached.questions
        assert len(suggestion_agent.calls) == 1
        assert [message.sequence for message in messages] == [1, 2, 3, 4, 5]
        assert messages[-1].source_message_id == messages[-2].id
        assert messages[-1].payload["source_message_id"] == str(
            messages[-2].id
        )
        assert len(messages[-1].payload["questions"]) == 3

        # 关闭功能后，即使已有缓存也应返回空列表，且不再次调用追问模型。
        disabled_service = ChatService(
            session_repository=session_repository,
            message_repository=message_repository,
            divination_repository=divination_repository,
            chatbot=runtime,  # type: ignore[arg-type]
            agent_session_factory=agent_sessions,
            divination_service=divination_service,
            chat_divination_workflow=workflow,
            session=session,
            suggested_question_agent=suggestion_agent,
            suggestions_enabled=False,
        )
        disabled = await disabled_service.generate_suggestions(
            session_id=created.id,
            user_id=user_id,
            assistant_message_id=assistant_message_id,
        )
        assert disabled.questions == []
        assert disabled.cached is False
        assert len(suggestion_agent.calls) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_chat_service_defers_tool_call_persistence_until_tool_finishes(
    tmp_path,
):
    """防止 Agent 工具与事件投影并发使用同一个 AsyncSession。"""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'tool-concurrency.db').as_posix()}",
        poolclass=NullPool,
    )
    enable_sqlite_foreign_keys(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as session:
        user = User()
        session.add(user)
        await session.commit()
        user_id = user.id

    async with factory() as session:
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
        runtime = BackgroundToolRuntime()
        service = ChatService(
            session_repository=session_repository,
            message_repository=message_repository,
            divination_repository=divination_repository,
            chatbot=runtime,  # type: ignore[arg-type]
            agent_session_factory=AgentSessionFactory(
                engine=engine,
                recent_limit=10,
            ),
            divination_service=divination_service,
            chat_divination_workflow=workflow,
            session=session,
        )
        created = await service.create_session(ChatSessionCreate(), user_id)

        original_persist_tool_call = service._persist_tool_call

        async def assert_tool_finished_before_persist(*args, **kwargs):
            assert runtime.tool_task is not None
            assert runtime.tool_task.done()
            await original_persist_tool_call(*args, **kwargs)

        service._persist_tool_call = (  # type: ignore[method-assign]
            assert_tool_finished_before_persist
        )

        events = [
            event
            async for event in service.stream_reply(
                session_id=created.id,
                user_id=user_id,
                user_message="帮我随机起一卦看工作机会",
            )
        ]
        messages = await service.list_messages(created.id, user_id)

        assert events[-1].event_type == ChatEventType.MESSAGE_COMPLETED
        assert [message.message_type for message in messages] == [
            "text",
            "tool_call",
            "tool_result",
            "text",
        ]

    await engine.dispose()


@pytest.mark.asyncio
async def test_chat_service_explicit_cancel_persists_notice_and_rolls_back_sdk_turn(
    tmp_path,
):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'cancel-chat.db').as_posix()}",
        poolclass=NullPool,
    )
    enable_sqlite_foreign_keys(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with factory() as session:
        user = User()
        session.add(user)
        await session.commit()
        user_id = user.id

    async with factory() as session:
        sessions = ChatSessionRepository(session)
        messages = ChatMessageRepository(session)
        divinations = DivinationRepository(session)
        divination_service = DivinationService(divinations, session)
        runtime = CancellableRuntime()
        registry = ChatRunRegistry()
        agent_sessions = AgentSessionFactory(engine=engine, recent_limit=10)
        service = ChatService(
            session_repository=sessions,
            message_repository=messages,
            divination_repository=divinations,
            chatbot=runtime,  # type: ignore[arg-type]
            agent_session_factory=agent_sessions,
            divination_service=divination_service,
            chat_divination_workflow=ChatDivinationWorkflow(
                chat_session_repository=sessions,
                divination_service=divination_service,
                session=session,
            ),
            session=session,
            run_registry=registry,
        )
        created = await service.create_session(ChatSessionCreate(), user_id)
        request_id = uuid.uuid4()
        await service.prepare_run(
            request_id=request_id,
            session_id=created.id,
            user_id=user_id,
        )

        async def consume_stream():
            return [
                event
                async for event in service.stream_reply(
                    session_id=created.id,
                    user_id=user_id,
                    user_message="我还没有输入完",
                    request_id=request_id,
                )
            ]

        stream_task = asyncio.create_task(consume_stream())
        await asyncio.wait_for(runtime.started.wait(), timeout=2)
        cancelled = await service.cancel_run(
            request_id=request_id,
            session_id=created.id,
            user_id=user_id,
        )

        assert cancelled.status == "cancelled"
        with pytest.raises(asyncio.CancelledError):
            await stream_task

        persisted = await service.list_messages(created.id, user_id)
        assert [(item.role, item.status, item.content) for item in persisted] == [
            ("user", "cancelled", "我还没有输入完"),
            ("assistant", "cancelled", "已停止本次回答。"),
        ]
        assert await agent_sessions.create(created.id).get_items() == []

        repeated = await service.cancel_run(
            request_id=request_id,
            session_id=created.id,
            user_id=user_id,
        )
        assert repeated.status == "already_finished"

    await engine.dispose()
