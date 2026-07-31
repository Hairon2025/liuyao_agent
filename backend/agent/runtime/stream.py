"""把 Agents SDK 流式事件转换为项目稳定的 ChatEvent。"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from agents import RawResponsesStreamEvent, RunItemStreamEvent
from agents.items import ToolCallItem, ToolCallOutputItem
from agents.result import RunResultStreaming
from openai.types.responses import ResponseTextDeltaEvent

from backend.agent.runtime.context import AgentRunContext
from backend.schema.agent import ChatEvent, ChatEventType, ToolResult

_VISIBLE_TOOLS = {
    "process_divination_request",
    "cancel_divination_request",
    "get_divination",
    "list_divinations",
}


class AgentStreamAdapter:
    """把 SDK 文本和业务 Function Tool 事件转换成前端协议。"""

    async def stream(
        self,
        result: RunResultStreaming,
        context: AgentRunContext,
    ) -> AsyncIterator[ChatEvent]:
        calls: dict[str, tuple[str, Any]] = {}

        async for event in result.stream_events():
            if (
                isinstance(event, RawResponsesStreamEvent)
                and isinstance(event.data, ResponseTextDeltaEvent)
                and event.data.delta
            ):
                yield ChatEvent(
                    event_type=ChatEventType.TEXT_DELTA,
                    content=event.data.delta,
                )
                continue

            if not isinstance(event, RunItemStreamEvent):
                continue
            if event.name == "tool_called" and isinstance(
                event.item,
                ToolCallItem,
            ):
                tool_name = event.item.tool_name
                call_id = event.item.call_id
                if (
                    tool_name not in _VISIBLE_TOOLS
                    or call_id is None
                ):
                    continue
                arguments = self._tool_arguments(event.item.raw_item)
                calls[call_id] = (tool_name, arguments)
                yield ChatEvent(
                    event_type=ChatEventType.TOOL_CALL_STARTED,
                    tool_call_id=call_id,
                    tool_name=tool_name,
                    tool_arguments=arguments,
                )
                continue

            if event.name == "tool_output" and isinstance(
                event.item,
                ToolCallOutputItem,
            ):
                call_id = event.item.call_id
                if call_id is None or call_id not in calls:
                    continue
                tool_name, _ = calls[call_id]
                tool_result = self._tool_result(event.item.output)
                self._update_context(context, tool_result)
                yield ChatEvent(
                    event_type=(
                        ChatEventType.TOOL_CALL_COMPLETED
                        if tool_result.success
                        else ChatEventType.TOOL_CALL_FAILED
                    ),
                    tool_call_id=call_id,
                    tool_name=tool_name,
                    tool_result=tool_result,
                )

        final_output = result.final_output
        if isinstance(final_output, str) and final_output.strip():
            yield ChatEvent(
                event_type=ChatEventType.MESSAGE_COMPLETED,
                content=final_output,
            )

    @staticmethod
    def _tool_arguments(raw_item: object) -> Any:
        raw_arguments = (
            raw_item.get("arguments")
            if isinstance(raw_item, dict)
            else getattr(raw_item, "arguments", None)
        )
        if not isinstance(raw_arguments, str):
            return {}
        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _tool_result(output: object) -> ToolResult:
        if isinstance(output, str):
            try:
                return ToolResult.model_validate_json(output)
            except ValueError:
                return ToolResult(
                    success=False,
                    model_content=output or "工具执行失败。",
                    error_code="tool_execution_error",
                    retryable=False,
                )
        return ToolResult(
            success=False,
            model_content="工具返回了无法识别的结果。",
            error_code="invalid_tool_output",
            retryable=False,
        )

    @staticmethod
    def _update_context(
        context: AgentRunContext,
        result: ToolResult,
    ) -> None:
        if not result.success or not isinstance(result.data, dict):
            return
        candidate = result.data.get("divination_id")
        if isinstance(candidate, str):
            context.active_divination_id = candidate
