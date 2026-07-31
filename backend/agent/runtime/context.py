"""Agents SDK RunContext：向工具注入可信业务依赖。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from backend.services.chat_divination_workflow import ChatDivinationWorkflow
from backend.services.divination import DivinationService


@dataclass
class AgentRunContext:
    """单次 Chatbot 运行上下文，不暴露为模型工具参数。"""

    user_id: uuid.UUID
    session_id: uuid.UUID
    divination_service: DivinationService
    chat_divination_workflow: ChatDivinationWorkflow
    active_divination_id: str | None = None
    workflow_state: dict[str, Any] | None = None
