"""最小 ReAct 执行循环。"""
from __future__ import annotations

from collections.abc import AsyncIterator

from backend.agent.model import ChatModelAdapter
from backend.agent.tools import (
    ToolArgumentsError,
    ToolNotFoundError,
    ToolRegistry,
)
from backend.schema.agent import (
    ChatEvent,
    ChatEventType,
    ChatMessageType,
    ChatRole,
    ChatTurnInput,
    ModelFinishReason,
    ModelMessage,
    ModelRequest,
    ModelStreamEvent,
    ModelStreamEventType,
    ToolContext,
    ToolResult,
)


class ReActRunner:
    """在模型和已注册工具之间执行有限步数的 ReAct 循环。"""

    def __init__(
        self,
        *,
        model_adapter: ChatModelAdapter,
        tool_registry: ToolRegistry,
        instructions: str | None = None,
        max_steps: int = 6,
    ):
        if max_steps < 1:
            raise ValueError("max_steps 必须大于等于 1")
        self._model_adapter = model_adapter
        self._tool_registry = tool_registry
        self._instructions = instructions
        self._max_steps = max_steps

    async def run(
        self,
        turn_input: ChatTurnInput,
    ) -> AsyncIterator[ChatEvent]:
        """执行一轮对话并输出统一 ChatEvent。"""
        messages = self._build_initial_messages(turn_input)
        seen_tool_call_ids: set[str] = set()
        visible_text_chunks: list[str] = []
        active_divination_id = turn_input.active_divination_id

        for _ in range(self._max_steps):
            request = ModelRequest(
                messages=messages,
                tools=list(self._tool_registry.definitions()),
                instructions=self._instructions,
                model=turn_input.model,
            )
            text_chunks: list[str] = []
            tool_calls: list[ModelStreamEvent] = []
            finish_reason: ModelFinishReason | None = None

            try:
                async for event in self._model_adapter.stream(request):
                    if finish_reason is not None:
                        yield self._protocol_error(
                            "模型在 step_completed 后仍然产生事件"
                        )
                        return

                    if event.event_type == ModelStreamEventType.TEXT_DELTA:
                        assert event.delta is not None
                        text_chunks.append(event.delta)
                        visible_text_chunks.append(event.delta)
                        yield ChatEvent(
                            event_type=ChatEventType.TEXT_DELTA,
                            content=event.delta,
                        )
                        continue

                    if event.event_type == ModelStreamEventType.TOOL_CALL:
                        assert event.tool_call_id is not None
                        if event.tool_call_id in seen_tool_call_ids:
                            yield self._protocol_error(
                                "模型产生了重复的 tool_call_id"
                            )
                            return
                        seen_tool_call_ids.add(event.tool_call_id)
                        tool_calls.append(event)
                        continue

                    if (
                        event.event_type
                        == ModelStreamEventType.STEP_COMPLETED
                    ):
                        assert event.finish_reason is not None
                        finish_reason = event.finish_reason
            except Exception:
                yield ChatEvent(
                    event_type=ChatEventType.ERROR,
                    content="模型调用失败。",
                    error_code="model_execution_error",
                    retryable=True,
                )
                return

            if finish_reason is None:
                yield self._protocol_error("模型事件流缺少 step_completed")
                return

            if finish_reason == ModelFinishReason.LENGTH:
                yield ChatEvent(
                    event_type=ChatEventType.ERROR,
                    content="模型输出因长度限制被截断。",
                    error_code="model_output_truncated",
                    retryable=True,
                )
                return

            if finish_reason == ModelFinishReason.STOP:
                if tool_calls:
                    yield self._protocol_error(
                        "finish_reason=stop 时不应包含工具调用"
                    )
                    return
                # MESSAGE_COMPLETED 必须与本轮已经发出的全部文本增量一致，
                # 包括模型在调用工具前产生的可见说明。
                full_content = "".join(visible_text_chunks)
                if not full_content:
                    yield ChatEvent(
                        event_type=ChatEventType.ERROR,
                        content="模型没有生成任何回答。",
                        error_code="empty_model_response",
                        retryable=True,
                    )
                    return
                yield ChatEvent(
                    event_type=ChatEventType.MESSAGE_COMPLETED,
                    content=full_content,
                )
                return

            if finish_reason != ModelFinishReason.TOOL_CALLS:
                yield self._protocol_error("模型返回了未知 finish_reason")
                return

            if not tool_calls:
                yield self._protocol_error(
                    "finish_reason=tool_calls 但没有工具调用"
                )
                return

            if text_chunks:
                messages.append(
                    ModelMessage(
                        role=ChatRole.ASSISTANT,
                        content="".join(text_chunks),
                    )
                )

            # 先写入同一步的全部工具调用，再追加工具结果。这样模型适配器
            # 可以将连续调用重新组合为供应商所需的单个 assistant turn。
            for tool_call in tool_calls:
                assert tool_call.tool_call_id is not None
                assert tool_call.tool_name is not None
                assert tool_call.tool_arguments is not None

                messages.append(
                    ModelMessage(
                        role=ChatRole.ASSISTANT,
                        message_type=ChatMessageType.TOOL_CALL,
                        tool_call_id=tool_call.tool_call_id,
                        tool_name=tool_call.tool_name,
                        payload=tool_call.tool_arguments,
                    )
                )

            for tool_call in tool_calls:
                assert tool_call.tool_call_id is not None
                assert tool_call.tool_name is not None
                assert tool_call.tool_arguments is not None

                yield ChatEvent(
                    event_type=ChatEventType.TOOL_CALL_STARTED,
                    tool_call_id=tool_call.tool_call_id,
                    tool_name=tool_call.tool_name,
                    tool_arguments=tool_call.tool_arguments,
                )

                result = await self._execute_tool(
                    turn_input,
                    tool_call,
                    active_divination_id=active_divination_id,
                )
                if result.success and isinstance(result.data, dict):
                    candidate = result.data.get("divination_id")
                    if isinstance(candidate, str):
                        # 让同一 ReAct 轮次中的后续工具立即看到新卦例。
                        active_divination_id = candidate
                event_type = (
                    ChatEventType.TOOL_CALL_COMPLETED
                    if result.success
                    else ChatEventType.TOOL_CALL_FAILED
                )
                yield ChatEvent(
                    event_type=event_type,
                    tool_call_id=tool_call.tool_call_id,
                    tool_name=tool_call.tool_name,
                    tool_result=result,
                )
                messages.append(
                    ModelMessage(
                        role=ChatRole.TOOL,
                        message_type=ChatMessageType.TOOL_RESULT,
                        content=result.model_content,
                        tool_call_id=tool_call.tool_call_id,
                        tool_name=tool_call.tool_name,
                        payload=result.model_dump(mode="json"),
                    )
                )

        yield ChatEvent(
            event_type=ChatEventType.ERROR,
            content="Agent 已达到最大 ReAct 执行步数。",
            error_code="max_steps_exceeded",
            retryable=False,
        )

    async def _execute_tool(
        self,
        turn_input: ChatTurnInput,
        tool_call: ModelStreamEvent,
        *,
        active_divination_id: str | None,
    ) -> ToolResult:
        """执行单个工具，并把可预期异常转换为模型可观察结果。"""
        assert tool_call.tool_call_id is not None
        assert tool_call.tool_name is not None
        assert tool_call.tool_arguments is not None

        context = ToolContext(
            user_id=turn_input.user_id,
            session_id=turn_input.session_id,
            tool_call_id=tool_call.tool_call_id,
            active_divination_id=active_divination_id,
        )
        try:
            return await self._tool_registry.execute(
                tool_call.tool_name,
                context,
                tool_call.tool_arguments,
            )
        except ToolArgumentsError:
            return ToolResult(
                success=False,
                model_content=(
                    "工具参数不符合 Schema，请修正参数后重新调用。"
                ),
                error_code="invalid_tool_arguments",
                retryable=True,
            )
        except ToolNotFoundError:
            available = "、".join(self._tool_registry.names()) or "无"
            return ToolResult(
                success=False,
                model_content=f"工具未注册。当前可用工具：{available}。",
                error_code="unknown_tool",
                retryable=True,
            )
        except Exception:
            return ToolResult(
                success=False,
                model_content="工具执行失败，无法完成本次调用。",
                error_code="tool_execution_error",
                retryable=False,
            )

    @staticmethod
    def _build_initial_messages(
        turn_input: ChatTurnInput,
    ) -> list[ModelMessage]:
        """把存储无关的 ChatTurnInput 转为模型上下文消息。"""
        messages: list[ModelMessage] = []
        if turn_input.session_summary is not None:
            messages.append(
                ModelMessage(
                    role=ChatRole.SYSTEM,
                    message_type=ChatMessageType.SUMMARY,
                    content=turn_input.session_summary,
                )
            )
        messages.extend(
            ModelMessage(
                role=message.role,
                message_type=message.message_type,
                content=message.content,
                tool_call_id=message.tool_call_id,
                tool_name=message.tool_name,
                payload=message.payload,
            )
            for message in turn_input.recent_messages
        )
        messages.append(
            ModelMessage(
                role=ChatRole.USER,
                content=turn_input.user_message,
            )
        )
        return messages

    @staticmethod
    def _protocol_error(content: str) -> ChatEvent:
        return ChatEvent(
            event_type=ChatEventType.ERROR,
            content=content,
            error_code="model_protocol_error",
            retryable=False,
        )
