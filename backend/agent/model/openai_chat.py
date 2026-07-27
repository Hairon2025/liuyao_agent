"""OpenAI 兼容 Chat Completions 模型适配器。"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from backend.agent.model.base import ChatModelAdapter
from backend.config.settings import settings
from backend.schema.agent import (
    ChatMessageType,
    ChatRole,
    ModelFinishReason,
    ModelMessage,
    ModelRequest,
    ModelStreamEvent,
    ModelStreamEventType,
)


class ModelAdapterProtocolError(RuntimeError):
    """模型供应商返回了无法转换为内部协议的数据。"""


class OpenAIChatModelAdapter(ChatModelAdapter):
    """将 Chat Completions 流转换为模型无关事件。

    这里刻意使用 Chat Completions 而不是供应商特有的 Agent API，以便
    ``LLM_BASE_URL`` 指向兼容 OpenAI 协议的第三方服务时仍可工作。
    """

    def __init__(
        self,
        *,
        client: AsyncOpenAI | Any | None = None,
        default_model: str | None = None,
    ):
        # 延迟到首次生成时再创建客户端，使会话 CRUD 不依赖 LLM 凭据。
        self._client = client
        self._default_model = default_model or settings.llm_model

    async def stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        """请求模型并产出已聚合完成的工具调用事件。"""
        create_kwargs: dict[str, Any] = {
            "model": request.model or self._default_model,
            "messages": self._to_openai_messages(request),
            "stream": True,
        }
        if request.tools:
            create_kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in request.tools
            ]
            create_kwargs["tool_choice"] = "auto"

        client = self._get_client()
        response_stream = await client.chat.completions.create(
            **create_kwargs
        )
        tool_buffers: dict[int, dict[str, str]] = {}
        finish_reason: str | None = None

        async for chunk in response_stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            if delta.content:
                yield ModelStreamEvent(
                    event_type=ModelStreamEventType.TEXT_DELTA,
                    delta=delta.content,
                )

            for tool_delta in delta.tool_calls or ():
                buffer = tool_buffers.setdefault(
                    tool_delta.index,
                    {"id": "", "name": "", "arguments": ""},
                )
                if tool_delta.id:
                    buffer["id"] = tool_delta.id
                if tool_delta.function is not None:
                    if tool_delta.function.name:
                        buffer["name"] += tool_delta.function.name
                    if tool_delta.function.arguments:
                        buffer["arguments"] += tool_delta.function.arguments

            if choice.finish_reason is not None:
                finish_reason = choice.finish_reason

        for index in sorted(tool_buffers):
            buffer = tool_buffers[index]
            try:
                arguments = json.loads(buffer["arguments"] or "{}")
            except json.JSONDecodeError as exc:
                raise ModelAdapterProtocolError(
                    f"工具 {buffer['name'] or index} 的参数不是合法 JSON"
                ) from exc
            if not isinstance(arguments, dict):
                raise ModelAdapterProtocolError("工具参数必须是 JSON 对象")
            if not buffer["id"] or not buffer["name"]:
                raise ModelAdapterProtocolError(
                    "模型工具调用缺少 id 或 name"
                )
            yield ModelStreamEvent(
                event_type=ModelStreamEventType.TOOL_CALL,
                tool_call_id=buffer["id"],
                tool_name=buffer["name"],
                tool_arguments=arguments,
            )

        yield ModelStreamEvent(
            event_type=ModelStreamEventType.STEP_COMPLETED,
            finish_reason=self._map_finish_reason(finish_reason),
        )

    def _get_client(self) -> AsyncOpenAI | Any:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout_seconds,
            )
        return self._client

    @classmethod
    def _to_openai_messages(
        cls,
        request: ModelRequest,
    ) -> list[dict[str, Any]]:
        """转换消息，并把连续工具调用合并为一个 assistant turn。"""
        converted: list[dict[str, Any]] = []
        if request.instructions:
            converted.append(
                {"role": "system", "content": request.instructions}
            )

        index = 0
        while index < len(request.messages):
            message = request.messages[index]
            if message.message_type == ChatMessageType.TOOL_CALL:
                calls: list[dict[str, Any]] = []
                while (
                    index < len(request.messages)
                    and request.messages[index].message_type
                    == ChatMessageType.TOOL_CALL
                ):
                    call = request.messages[index]
                    if not isinstance(call.payload, dict):
                        raise ModelAdapterProtocolError(
                            "工具调用消息 payload 必须是 JSON 对象"
                        )
                    calls.append(
                        {
                            "id": call.tool_call_id,
                            "type": "function",
                            "function": {
                                "name": call.tool_name,
                                "arguments": json.dumps(
                                    call.payload,
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    )
                    index += 1
                converted.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": calls,
                    }
                )
                continue

            converted.append(cls._to_openai_message(message))
            index += 1
        return converted

    @staticmethod
    def _to_openai_message(message: ModelMessage) -> dict[str, Any]:
        if message.message_type == ChatMessageType.TOOL_RESULT:
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "content": message.content or "",
            }

        content = message.content or ""
        if message.message_type == ChatMessageType.SUMMARY:
            content = f"以下是此前会话的压缩摘要：\n{content}"
        role = (
            "system"
            if message.role == ChatRole.SYSTEM
            else message.role.value
        )
        return {"role": role, "content": content}

    @staticmethod
    def _map_finish_reason(reason: str | None) -> ModelFinishReason:
        if reason == "stop":
            return ModelFinishReason.STOP
        if reason == "tool_calls":
            return ModelFinishReason.TOOL_CALLS
        if reason == "length":
            return ModelFinishReason.LENGTH
        raise ModelAdapterProtocolError(
            f"模型返回了不支持的 finish_reason：{reason!r}"
        )
