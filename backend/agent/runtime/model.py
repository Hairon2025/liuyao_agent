"""Agents SDK 模型工厂。"""
from __future__ import annotations

from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel
from agents.models.interface import Model

from backend.config.settings import settings


class AgentModelFactory:
    """显式创建 OpenAI 兼容模型，避免修改 SDK 的进程级全局配置。"""

    def __init__(self, client: AsyncOpenAI | None = None):
        self._client = client

    def create(self, model_name: str | None = None) -> Model:
        """为一次 Agent 图构建绑定模型。"""
        return OpenAIChatCompletionsModel(
            model=model_name or settings.llm_model,
            openai_client=self._get_client(),
            # 兼容部分 OpenAI-compatible 服务的分片工具参数。
            buffer_streamed_tool_calls=True,
        )

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout_seconds,
            )
        return self._client
