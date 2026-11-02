"""Agents SDK 模型工厂。"""
from __future__ import annotations

from openai import AsyncOpenAI
from agents import ModelSettings, OpenAIChatCompletionsModel
from agents.models.interface import Model
from openai.types.shared.reasoning import Reasoning

from backend.config.settings import settings


def non_thinking_model_settings() -> ModelSettings:
    """为无需复杂推理的角色显式关闭 DeepSeek 思考模式。

    同时设置 OpenAI-compatible 的 ``reasoning_effort`` 与 DeepSeek 专用
    ``thinking`` 参数，确保不同兼容层都不会回退到默认的 high thinking。
    """
    return ModelSettings(
        reasoning=Reasoning(effort="none"),
        extra_body={"thinking": {"type": "disabled"}},
    )


class AgentModelFactory:
    """显式创建 OpenAI 兼容模型，避免修改 SDK 的进程级全局配置。"""

    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        default_model: str | None = None,
    ):
        self._client = client
        self._api_key = api_key or settings.llm_api_key
        self._base_url = base_url or settings.llm_base_url
        self._timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.llm_timeout_seconds
        )
        self._default_model = default_model or settings.llm_model

    def create(self, model_name: str | None = None) -> Model:
        """为一次 Agent 图构建绑定模型。"""
        return OpenAIChatCompletionsModel(
            model=model_name or self._default_model,
            openai_client=self._get_client(),
            # 兼容部分 OpenAI-compatible 服务的分片工具参数。
            buffer_streamed_tool_calls=True,
        )

    @property
    def default_model(self) -> str:
        return self._default_model

    @property
    def base_url(self) -> str:
        return self._base_url

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout_seconds,
            )
        return self._client
