"""已有排盘请求首次正式解读的 Function Tool 测试。"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from agents.tool_context import ToolContext

from backend.agent.runtime.context import AgentRunContext
from backend.agent.tools.divination import request_initial_interpretation
from backend.schema.agent import ToolResult
from backend.schema.api.divination import InterpretationResult
from backend.services.exceptions import DivinationNotFoundError


class FakeDivinationService:
    def __init__(
        self,
        *,
        detail: str | None = None,
        markdown_content: str | None = "# 排盘",
        not_found: bool = False,
    ):
        self.detail = detail
        self.markdown_content = markdown_content
        self.not_found = not_found
        self.generated: list[tuple[str, uuid.UUID]] = []

    async def get(self, divination_id, user_id):
        if self.not_found:
            raise DivinationNotFoundError(divination_id)
        return SimpleNamespace(
            interpretation=InterpretationResult(detail=self.detail),
            markdown_content=self.markdown_content,
        )

    async def generate_markdown(self, divination_id, user_id):
        self.generated.append((divination_id, user_id))
        return "# 新生成排盘"


async def invoke_tool(
    service: FakeDivinationService,
    *,
    active_divination_id: str | None,
) -> tuple[ToolResult, AgentRunContext]:
    context = AgentRunContext(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        divination_service=service,  # type: ignore[arg-type]
        chat_divination_workflow=object(),  # type: ignore[arg-type]
        active_divination_id=active_divination_id,
    )
    tool_context = ToolContext(
        context,
        tool_name="request_initial_interpretation",
        tool_call_id="call-interpret",
        tool_arguments="{}",
    )
    raw_output = await request_initial_interpretation.on_invoke_tool(
        tool_context,
        "{}",
    )
    return ToolResult.model_validate_json(raw_output), context


@pytest.mark.asyncio
async def test_request_initial_interpretation_returns_ready_and_markdown():
    divination_id = "d" * 32
    service = FakeDivinationService(markdown_content=None)

    result, context = await invoke_tool(
        service,
        active_divination_id=divination_id,
    )

    assert result.success is True
    assert result.data == {
        "status": "ready_for_interpretation",
        "divination_id": divination_id,
    }
    assert service.generated == [(divination_id, context.user_id)]


@pytest.mark.asyncio
async def test_request_initial_interpretation_does_not_overwrite_report():
    service = FakeDivinationService(detail="已经保存的正式报告")

    result, _ = await invoke_tool(
        service,
        active_divination_id="e" * 32,
    )

    assert result.success is True
    assert result.data["status"] == "already_interpreted"
    assert "已经保存的正式报告" in result.model_content
    assert service.generated == []


@pytest.mark.asyncio
async def test_request_initial_interpretation_checks_ownership():
    result, _ = await invoke_tool(
        FakeDivinationService(not_found=True),
        active_divination_id="f" * 32,
    )

    assert result.success is False
    assert result.error_code == "divination_not_found"
