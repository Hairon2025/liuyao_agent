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
    """
    在模型和已注册工具之间执行有限步数的 ReAct 循环。
    
    ReAct 模式：模型推理（Reason）→ 调用工具（Act）→ 观察结果 → 继续推理，直至得到最终答案。
    该执行器负责维护对话状态，协调模型流和工具调用，并输出标准化事件。
    """

    def __init__(
        self,
        *,
        model_adapter: ChatModelAdapter,      # 模型适配器，负责与具体 LLM 通信
        tool_registry: ToolRegistry,          # 工具注册表，存放所有可用工具及其实现
        instructions: str | None = None,      # 系统级指令（如角色设定、行为约束）
        max_steps: int = 3,                   # 最大 ReAct 迭代步数，防止无限循环
    ):
        if max_steps < 1:
            raise ValueError("max_steps 必须大于等于 1")
        self._model_adapter = model_adapter
        self._tool_registry = tool_registry
        self._instructions = instructions
        self._max_steps = max_steps

    async def run(
        self,
        turn_input: ChatTurnInput,            # 本轮对话输入，包含用户消息、历史、摘要等
    ) -> AsyncIterator[ChatEvent]:
        """
        执行一轮对话并输出统一 ChatEvent 事件流。
        
        事件类型包括：
        - TEXT_DELTA：模型生成的文本增量（流式）
        - TOOL_CALL_STARTED / COMPLETED / FAILED：工具调用生命周期
        - MESSAGE_COMPLETED：模型最终完整回答（仅当成功结束）
        - ERROR：各类错误（协议、模型、工具、步数超限等）
        """
        # 1. 构建初始消息列表（摘要 + 历史记录 + 用户最新输入）
        messages = self._build_initial_messages(turn_input)
        # 用于去重校验，记录已出现过的 tool_call_id
        seen_tool_call_ids: set[str] = set()
        # 收集本轮所有可见的文本增量（包括推理过程中的思考文字），最终可能作为完整回答
        visible_text_chunks: list[str] = []
        # 当前“活动卦例 ID”，用于在工具间传递状态（业务特定，若不需要可忽略）
        active_divination_id = turn_input.active_divination_id

        # 2. 开始 ReAct 主循环，最多执行 max_steps 次
        for _ in range(self._max_steps):
            # 构造模型请求：包含当前消息历史、可用工具定义、指令、模型名
            request = ModelRequest(
                messages=messages,
                tools=list(self._tool_registry.definitions()),
                instructions=self._instructions,
                model=turn_input.model,
            )

            text_chunks: list[str] = []       # 当前步骤的文本增量
            tool_calls: list[ModelStreamEvent] = []  # 当前步骤的工具调用事件
            finish_reason: ModelFinishReason | None = None  # 模型结束原因

            # 3. 调用模型适配器，流式获取响应
            try:
                async for event in self._model_adapter.stream(request):
                    # 一旦收到 STEP_COMPLETED，后续不应再有任何事件，否则协议错误
                    if finish_reason is not None:
                        yield self._protocol_error(
                            "模型在 step_completed 后仍然产生事件"
                        )
                        return

                    # 3a. 文本增量：直接转发给上层，并缓存
                    if event.event_type == ModelStreamEventType.TEXT_DELTA:
                        assert event.delta is not None
                        text_chunks.append(event.delta)
                        visible_text_chunks.append(event.delta)
                        yield ChatEvent(
                            event_type=ChatEventType.TEXT_DELTA,
                            content=event.delta,
                        )
                        continue

                    # 3b. 工具调用：缓存，并校验 ID 唯一性
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

                    # 3c. 步骤完成：记录结束原因
                    if event.event_type == ModelStreamEventType.STEP_COMPLETED:
                        assert event.finish_reason is not None
                        finish_reason = event.finish_reason
            except Exception:
                # 模型调用出现未预期异常（如网络断开），反馈可重试错误
                yield ChatEvent(
                    event_type=ChatEventType.ERROR,
                    content="模型调用失败。",
                    error_code="model_execution_error",
                    retryable=True,
                )
                return

            # 4. 校验：必须收到有效的 finish_reason
            if finish_reason is None:
                yield self._protocol_error("模型事件流缺少 step_completed")
                return

            # 5. 根据结束原因分支处理

            # 5a. 长度截断：报错结束
            if finish_reason == ModelFinishReason.LENGTH:
                yield ChatEvent(
                    event_type=ChatEventType.ERROR,
                    content="模型输出因长度限制被截断。",
                    error_code="model_output_truncated",
                    retryable=True,
                )
                return

            # 5b. 正常停止（无工具调用）：输出最终完整回答
            if finish_reason == ModelFinishReason.STOP:
                if tool_calls:
                    yield self._protocol_error(
                        "finish_reason=stop 时不应包含工具调用"
                    )
                    return
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

            # 5c. 工具调用分支：模型要求执行工具
            if finish_reason != ModelFinishReason.TOOL_CALLS:
                yield self._protocol_error("模型返回了未知 finish_reason")
                return

            if not tool_calls:
                yield self._protocol_error(
                    "finish_reason=tool_calls 但没有工具调用"
                )
                return

            # 6. 处理工具调用：将本次模型生成的文本（如果有）作为 assistant 消息追加到历史
            if text_chunks:
                messages.append(
                    ModelMessage(
                        role=ChatRole.ASSISTANT,
                        content="".join(text_chunks),
                    )
                )

            # 7. 先向消息历史追加所有工具调用记录（assistant 角色的 tool_call 消息）
            #    这样模型适配器在下一轮请求时可以正确组合工具调用（供应商通常要求连续）
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

            # 8. 串行执行每个工具调用（注意：是串行，可考虑并发优化）
            for tool_call in tool_calls:
                assert tool_call.tool_call_id is not None
                assert tool_call.tool_name is not None
                assert tool_call.tool_arguments is not None

                # 通知上层工具开始执行
                yield ChatEvent(
                    event_type=ChatEventType.TOOL_CALL_STARTED,
                    tool_call_id=tool_call.tool_call_id,
                    tool_name=tool_call.tool_name,
                    tool_arguments=tool_call.tool_arguments,
                )

                # 执行工具，传入当前上下文（包含可能已更新的 divination_id）
                result = await self._execute_tool(
                    turn_input,
                    tool_call,
                    active_divination_id=active_divination_id,
                )

                # 如果工具成功返回了一个新的 divination_id，则更新上下文（供后续工具使用）
                if result.success and isinstance(result.data, dict):
                    candidate = result.data.get("divination_id")
                    if isinstance(candidate, str):
                        active_divination_id = candidate

                # 根据执行结果发出完成或失败事件
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

                # 将工具结果追加为 TOOL 角色的消息，以便模型在下一次请求时看到结果
                messages.append(
                    ModelMessage(
                        role=ChatRole.TOOL,
                        message_type=ChatMessageType.TOOL_RESULT,
                        content=result.model_content,          # 模型可读的文本摘要
                        tool_call_id=tool_call.tool_call_id,
                        tool_name=tool_call.tool_name,
                        payload=result.model_dump(mode="json"), # 完整结构化数据
                    )
                )

            # 本轮结束，回到循环开头，继续下一轮推理（模型将看到工具结果）

        # 9. 超出最大步数，报错终止（不可重试）
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
        """
        执行单个工具，并将可预期的异常转换为标准 ToolResult。
        
        此方法捕获工具参数错误、工具未找到、以及其他运行时异常，
        返回包含错误代码和可重试标志的 ToolResult，避免中断整个循环。
        """
        assert tool_call.tool_call_id is not None
        assert tool_call.tool_name is not None
        assert tool_call.tool_arguments is not None

        # 构建工具执行上下文
        context = ToolContext(
            user_id=turn_input.user_id,
            session_id=turn_input.session_id,
            tool_call_id=tool_call.tool_call_id,
            active_divination_id=active_divination_id,
        )
        try:
            # 通过注册表执行具体工具
            return await self._tool_registry.execute(
                tool_call.tool_name,
                context,
                tool_call.tool_arguments,
            )
        except ToolArgumentsError:
            # 参数不符合 Schema，可重试（修改参数后重试）
            return ToolResult(
                success=False,
                model_content="工具参数不符合 Schema，请修正参数后重新调用。",
                error_code="invalid_tool_arguments",
                retryable=True,
            )
        except ToolNotFoundError:
            # 工具未注册，可重试（但需用户更改工具名）
            available = "、".join(self._tool_registry.names()) or "无"
            return ToolResult(
                success=False,
                model_content=f"工具未注册。当前可用工具：{available}。",
                error_code="unknown_tool",
                retryable=True,
            )
        except Exception:
            # 其他未预期异常，通常不可重试（如内部逻辑错误）
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
        """
        将业务输入（ChatTurnInput）转换为模型所需的消息列表。
        
        顺序：系统摘要（若有）→ 历史消息 → 用户最新消息。
        这样保证模型能感知完整对话上下文。
        """
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
        """生成协议错误事件，不可重试。"""
        return ChatEvent(
            event_type=ChatEventType.ERROR,
            content=content,
            error_code="model_protocol_error",
            retryable=False,
        )