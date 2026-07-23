"""LLM 客户端封装（统一入口，供 Agent 调用）"""
from typing import Optional


class LLMClient:
    """统一的 LLM 调用客户端。

    具体实现由后续 Agent 层决定（OpenAI / Anthropic / 本地模型等）。
    此处仅定义接口，避免 Agent 强依赖具体厂商。
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: str = "gpt-4o"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    async def chat(self, system: str, user: str, **kwargs) -> str:
        """发送一次对话请求，返回模型回复文本。

        Args:
            system: 系统提示词
            user: 用户输入
            **kwargs: 模型参数（temperature、max_tokens 等）

        Returns:
            模型生成的文本
        """
        raise NotImplementedError("LLMClient.chat 需在具体实现中重写")
