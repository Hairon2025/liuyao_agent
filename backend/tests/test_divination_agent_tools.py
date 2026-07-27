"""六爻 Chatbot 工具测试。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.agent.tools import (
    CreateDivinationTool,
    GetDivinationTool,
    ListDivinationsTool,
)
from backend.schema.agent import ToolContext


class FakeDivinationService:
    def __init__(self):
        self.created = []
        self.generated = []

    async def create(self, request, user_id):
        self.created.append((request, user_id))
        return SimpleNamespace(
            divination_id="d" * 32,
            markdown_content="# 排盘",
            paipan=SimpleNamespace(
                question=request.question,
                qigua_time=request.time or datetime.now(timezone.utc),
                ben_gua=SimpleNamespace(name="乾为天"),
            ),
        )

    async def get(self, divination_id, user_id):
        return SimpleNamespace(
            divination_id=divination_id,
            markdown_content=None,
            paipan=SimpleNamespace(
                question="工作如何",
                qigua_time=datetime(2026, 7, 27, tzinfo=timezone.utc),
                ben_gua=SimpleNamespace(name="乾为天"),
            ),
            interpretation=None,
        )

    async def generate_markdown(self, divination_id, user_id):
        self.generated.append((divination_id, user_id))
        return "# 后生成的排盘"

    async def list_summaries(self, user_id, *, limit):
        return [{"divination_id": "d" * 32, "question": "工作如何"}][
            :limit
        ]


def _context(active_divination_id=None):
    return ToolContext(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        tool_call_id="call-1",
        active_divination_id=active_divination_id,
    )


@pytest.mark.asyncio
async def test_create_divination_tool_validates_and_returns_active_id():
    service = FakeDivinationService()
    context = _context()
    tool = CreateDivinationTool(service)  # type: ignore[arg-type]

    result = await tool.run(
        context,
        {
            "method": "manual",
            "question": " 工作如何 ",
            "numbers": [1, 2, 3, 4, 1, 2],
            "time": "2026-07-27T10:00:00+08:00",
        },
    )

    assert result.success is True
    assert result.data["divination_id"] == "d" * 32
    assert service.created[0][0].question == "工作如何"
    assert service.created[0][1] == context.user_id


@pytest.mark.asyncio
async def test_get_divination_tool_uses_active_session_divination():
    service = FakeDivinationService()
    context = _context("a" * 32)
    tool = GetDivinationTool(service)  # type: ignore[arg-type]

    result = await tool.run(context, {})

    assert result.success is True
    assert "# 后生成的排盘" in result.model_content
    assert service.generated[0][0] == "a" * 32


@pytest.mark.asyncio
async def test_list_divinations_tool_returns_structured_records():
    service = FakeDivinationService()
    tool = ListDivinationsTool(service)  # type: ignore[arg-type]

    result = await tool.run(_context(), {"limit": 5})

    assert result.success is True
    assert result.data[0]["question"] == "工作如何"
