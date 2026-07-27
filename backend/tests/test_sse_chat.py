"""ChatEvent SSE 编码测试。"""
from __future__ import annotations

import pytest

from backend.schema.agent import ChatEvent, ChatEventType
from backend.utils.sse import SSE_DONE, chat_events_to_sse


@pytest.mark.asyncio
async def test_chat_events_use_named_sse_and_done_event():
    async def events():
        yield ChatEvent(
            event_type=ChatEventType.TEXT_DELTA,
            content="第一行\n第二行",
        )
        yield ChatEvent(
            event_type=ChatEventType.MESSAGE_COMPLETED,
            content="第一行\n第二行",
        )

    chunks = [chunk async for chunk in chat_events_to_sse(events())]

    assert chunks[0].startswith("event: text_delta\n")
    assert '"event_type":"text_delta"' in chunks[0]
    assert chunks[-1] == f"event: done\ndata: {SSE_DONE}\n\n"
