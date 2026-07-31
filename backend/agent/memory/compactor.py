"""把旧 SDK Session Items 压缩为长期记忆。"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.memory_summary_agent import MemorySummaryAgent
from backend.models.agent_session import AgentMessageRecord
from backend.models.user import utc_now
from backend.repositories.agent_memory import AgentMemoryRepository
from backend.repositories.chat_session import ChatSessionRepository
from backend.services.exceptions import ChatSessionNotFoundError
from backend.utils.logger import logger


@dataclass(frozen=True)
class MemoryCompactionResult:
    """一次压缩检查的结果。"""

    summary: str | None
    compacted: bool
    compacted_items: int = 0
    retained_items: int = 0


class ChatMemoryCompactor:
    """按 SDK Item 数量触发摘要，并在摘要落库后删除已覆盖的原始 Item。"""

    def __init__(
        self,
        *,
        session_repository: ChatSessionRepository,
        memory_repository: AgentMemoryRepository,
        summary_agent: MemorySummaryAgent,
        session: AsyncSession,
        trigger_items: int,
        keep_recent_items: int,
        input_max_chars: int,
        context_recent_limit: int,
    ):
        if trigger_items < 2:
            raise ValueError("trigger_items 必须大于等于 2")
        if keep_recent_items < 1 or keep_recent_items >= trigger_items:
            raise ValueError(
                "keep_recent_items 必须大于等于 1 且小于 trigger_items"
            )
        if trigger_items > context_recent_limit:
            raise ValueError(
                "trigger_items 不能大于 chat_context_recent_limit"
            )
        if input_max_chars < 1000:
            raise ValueError("input_max_chars 必须大于等于 1000")
        self._session_repository = session_repository
        self._memory_repository = memory_repository
        self._summary_agent = summary_agent
        self._session = session
        self._trigger_items = trigger_items
        self._keep_recent_items = keep_recent_items
        self._input_max_chars = input_max_chars

    async def compact_if_needed(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> MemoryCompactionResult:
        chat_session = await self._session_repository.get_for_user(
            session_id,
            user_id,
        )
        if chat_session is None:
            raise ChatSessionNotFoundError(str(session_id))

        records = await self._memory_repository.list_for_session(
            str(session_id)
        )
        if len(records) < self._trigger_items:
            return MemoryCompactionResult(
                summary=chat_session.summary,
                compacted=False,
                retained_items=len(records),
            )

        retain_start = self._find_safe_retain_start(records)
        if retain_start == 0:
            # 单个超长轮次也不能拆开；本轮先保留全部 Item。
            return MemoryCompactionResult(
                summary=chat_session.summary,
                compacted=False,
                retained_items=len(records),
            )

        candidates, normalized_items = self._select_candidates_within_budget(
            records[:retain_start]
        )
        if not candidates:
            # 第一完整轮本身已超过摘要输入预算时不删除任何原始记录。
            return MemoryCompactionResult(
                summary=chat_session.summary,
                compacted=False,
                retained_items=len(records),
            )

        retained_count = len(records) - len(candidates)
        cutoff_id = candidates[-1].id
        expected_boundary = chat_session.summary_through_agent_message_id
        previous_summary = chat_session.summary

        # 模型调用期间不持有数据库事务；摘要失败时原始 Item 完全不变。
        await self._session.commit()
        memory = await self._summary_agent.summarize(
            previous_memory=previous_summary,
            conversation_items=normalized_items,
        )
        serialized = memory.model_dump_json()

        updated = (
            await self._session_repository.update_summary_if_boundary_matches(
                session_id=session_id,
                user_id=user_id,
                expected_agent_message_id=expected_boundary,
                summary=serialized,
                through_agent_message_id=cutoff_id,
                summary_updated_at=utc_now(),
            )
        )
        if not updated:
            # 另一请求已经完成压缩；丢弃本次生成结果并读取胜出的摘要。
            await self._session.rollback()
            latest = await self._session_repository.get_for_user(
                session_id,
                user_id,
            )
            return MemoryCompactionResult(
                summary=latest.summary if latest else previous_summary,
                compacted=False,
                retained_items=len(records),
            )

        deleted = await self._memory_repository.delete_through(
            session_id=str(session_id),
            through_id=cutoff_id,
        )
        await self._session.commit()
        logger.info(
            "会话 %s 已压缩 %s 条 SDK Item，按完整轮次保留最近 %s 条",
            session_id,
            deleted,
            retained_count,
        )
        return MemoryCompactionResult(
            summary=serialized,
            compacted=True,
            compacted_items=deleted,
            retained_items=retained_count,
        )

    def _find_safe_retain_start(
        self,
        records: list[AgentMessageRecord],
    ) -> int:
        """从最低保留数量向前寻找用户消息，避免拆散一次 Agent 工具循环。"""

        index = len(records) - self._keep_recent_items
        while index > 0:
            item = self._deserialize(records[index].message_data)
            if isinstance(item, dict) and item.get("role") == "user":
                return index
            index -= 1
        return 0

    def _select_candidates_within_budget(
        self,
        records: list[AgentMessageRecord],
    ) -> tuple[list[AgentMessageRecord], list[str]]:
        """在字符预算内选取完整用户轮次，返回实际可安全删除的记录。"""

        turns: list[list[AgentMessageRecord]] = []
        current_turn: list[AgentMessageRecord] = []
        for record in records:
            item = self._deserialize(record.message_data)
            if (
                current_turn
                and isinstance(item, dict)
                and item.get("role") == "user"
            ):
                turns.append(current_turn)
                current_turn = []
            current_turn.append(record)
        if current_turn:
            turns.append(current_turn)

        selected_records: list[AgentMessageRecord] = []
        normalized: list[str] = []
        used = 0
        for turn in turns:
            turn_texts = [
                text
                for record in turn
                if (
                    text := self._normalize_item(
                        self._deserialize(record.message_data)
                    )
                )
            ]
            turn_size = sum(len(text) for text in turn_texts)
            if used + turn_size > self._input_max_chars:
                break
            selected_records.extend(turn)
            normalized.extend(turn_texts)
            used += turn_size
        return selected_records, normalized

    @staticmethod
    def _deserialize(raw: str) -> Any:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    @staticmethod
    def _normalize_item(item: Any) -> str:
        if not isinstance(item, dict):
            return f"历史记录：{str(item)[:1000]}"

        role = item.get("role")
        item_type = item.get("type")
        content = item.get("content")
        if role in {"user", "assistant", "system"}:
            text = ChatMemoryCompactor._content_text(content)
            return f"{role}：{text[:2000]}" if text else ""
        if item_type in {"function_call", "tool_call"}:
            name = item.get("name") or item.get("tool_name") or "unknown"
            arguments = item.get("arguments") or item.get("args")
            return (
                f"工具调用 {name}："
                f"{json.dumps(arguments, ensure_ascii=False, default=str)[:1000]}"
            )
        if item_type in {"function_call_output", "tool_result"}:
            output = item.get("output") or item.get("content")
            return f"工具结果：{str(output)[:1600]}"
        return (
            "SDK Item："
            f"{json.dumps(item, ensure_ascii=False, default=str)[:1200]}"
        )

    @staticmethod
    def _content_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return str(content or "")
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
