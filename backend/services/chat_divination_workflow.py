"""Chatbot 多轮起卦的确定性业务工作流。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.repositories.chat_session import ChatSessionRepository
from backend.schema.agent.workflow import (
    CoinFace,
    ChatWorkflowState,
    DivinationDraft,
    DivinationTimeMode,
    DivinationWorkflowOutcome,
)
from backend.schema.api.divination import QiguaMethod, QiguaRequest
from backend.services.divination import DivinationService
from backend.services.exceptions import ChatSessionNotFoundError


class ChatDivinationWorkflow:
    """合并起卦草稿；参数完整后创建卦例并绑定当前会话。"""

    def __init__(
        self,
        *,
        chat_session_repository: ChatSessionRepository,
        divination_service: DivinationService,
        session: AsyncSession,
    ):
        self._chat_session_repository = chat_session_repository
        self._divination_service = divination_service
        self._session = session

    async def process(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        question: str | None = None,
        method: QiguaMethod | None = None,
        time_mode: DivinationTimeMode | None = None,
        time: datetime | None = None,
        numbers: list[int] | None = None,
        coin_tosses: list[list[CoinFace]] | None = None,
    ) -> DivinationWorkflowOutcome:
        """合并本轮参数；缺失时保存草稿，完整时执行固定起卦流程。"""
        chat_session = await self._chat_session_repository.get_for_user(
            session_id,
            user_id,
        )
        if chat_session is None:
            raise ChatSessionNotFoundError(str(session_id))

        state = self._load_state(chat_session.workflow_state)
        draft = state.payload.model_copy(deep=True)
        previous_method = draft.method

        if question is not None:
            draft.question = question.strip() or None
        if method is not None:
            draft.method = method
        if time_mode is not None:
            draft.time_mode = time_mode
        if time is not None:
            draft.time = time
            draft.time_mode = "specified"
        if numbers is not None:
            draft.numbers = numbers
        if coin_tosses is not None:
            draft.coin_tosses.extend(coin_tosses)

        if method is not None and method != previous_method:
            self._clear_incompatible_cast_data(draft)

        if draft.time_mode == "now":
            # “现在”在真正起卦时解析，避免收集其他字段期间时间变旧。
            draft.time = None

        self._validate_draft_values(draft)
        missing_fields = self._missing_fields(draft)
        if missing_fields:
            state.payload = draft
            await self._chat_session_repository.update(
                chat_session,
                {"workflow_state": state.model_dump(mode="json")},
            )
            await self._session.commit()
            return DivinationWorkflowOutcome(
                status="needs_input",
                missing_fields=missing_fields,
                draft=draft,
            )

        assert draft.question is not None
        assert draft.method is not None
        numbers_for_request = self._numbers_for_request(draft)
        response = await self._divination_service.create(
            QiguaRequest(
                method=draft.method,
                question=draft.question,
                time=draft.time,
                numbers=numbers_for_request,
                generate_markdown=True,
            ),
            user_id,
        )
        await self._chat_session_repository.update(
            chat_session,
            {
                "active_divination_id": response.divination_id,
                "workflow_state": None,
            },
        )
        await self._session.commit()
        return DivinationWorkflowOutcome(
            status="created",
            divination_id=response.divination_id,
            hexagram_name=response.paipan.ben_gua.name,
            qigua_time=response.paipan.qigua_time,
            paipan_markdown=response.markdown_content,
        )

    async def cancel(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> bool:
        """取消当前未完成的起卦流程，保留已经完成的当前卦例。"""
        chat_session = await self._chat_session_repository.get_for_user(
            session_id,
            user_id,
        )
        if chat_session is None:
            raise ChatSessionNotFoundError(str(session_id))
        had_pending_state = chat_session.workflow_state is not None
        if had_pending_state:
            await self._chat_session_repository.update(
                chat_session,
                {"workflow_state": None},
            )
            await self._session.commit()
        return had_pending_state

    @staticmethod
    def _load_state(raw_state: object) -> ChatWorkflowState:
        if not isinstance(raw_state, dict):
            return ChatWorkflowState()
        try:
            return ChatWorkflowState.model_validate(raw_state)
        except ValueError:
            # 版本或结构不兼容时重新开始，不让损坏草稿阻塞整个会话。
            return ChatWorkflowState()

    @staticmethod
    def _missing_fields(draft: DivinationDraft) -> list[str]:
        missing: list[str] = []
        if draft.question is None:
            missing.append("question")
        if draft.method is None:
            missing.append("method")
        if draft.method in {
            QiguaMethod.MANUAL,
            QiguaMethod.COIN,
            QiguaMethod.TIME,
        } and draft.time_mode is None:
            missing.append("time_mode")
        if draft.time_mode == "specified" and draft.time is None:
            missing.append("time")
        if draft.method == QiguaMethod.MANUAL and draft.numbers is None:
            missing.append("numbers")
        if (
            draft.method == QiguaMethod.COIN
            and len(draft.coin_tosses) < 6
        ):
            missing.append("coin_tosses")
        return missing

    @staticmethod
    def _validate_draft_values(draft: DivinationDraft) -> None:
        if draft.numbers is not None:
            if draft.method != QiguaMethod.MANUAL:
                raise ValueError("只有 manual 起卦可以直接提供 numbers")
            if len(draft.numbers) != 6:
                raise ValueError("manual 必须提供从初爻到上爻的 6 个爻值")
            if any(number not in {1, 2, 3, 4} for number in draft.numbers):
                raise ValueError("爻值只能是 1、2、3、4")

        if draft.method != QiguaMethod.COIN and draft.coin_tosses:
            raise ValueError("只有 coin 起卦可以提供铜钱投掷结果")
        if len(draft.coin_tosses) > 6:
            raise ValueError("铜钱起卦最多接收 6 次投掷结果")
        if any(len(toss) != 3 for toss in draft.coin_tosses):
            raise ValueError("每次投掷必须包含 3 枚铜钱的结果")

    @staticmethod
    def _clear_incompatible_cast_data(draft: DivinationDraft) -> None:
        """切换起卦方式时清理其他方式留下的专属数据。"""
        if draft.method != QiguaMethod.MANUAL:
            draft.numbers = None
        if draft.method != QiguaMethod.COIN:
            draft.coin_tosses = []
        if draft.method == QiguaMethod.RANDOM:
            draft.time_mode = None
            draft.time = None

    @classmethod
    def _numbers_for_request(cls, draft: DivinationDraft) -> list[int] | None:
        if draft.method == QiguaMethod.MANUAL:
            return draft.numbers
        if draft.method == QiguaMethod.COIN:
            return [
                cls._coin_toss_to_line(toss)
                for toss in draft.coin_tosses
            ]
        return None

    @staticmethod
    def _coin_toss_to_line(toss: list[CoinFace]) -> int:
        """把三枚铜钱的字/花面确定性换算成一个爻值。"""
        flower_count = toss.count("花")
        return {
            0: 4,  # 三字：老阴
            1: 2,  # 两字一花：少阳
            2: 1,  # 一字两花：少阴
            3: 3,  # 三花：老阳
        }[flower_count]
