"""六爻解卦分析师：根据排盘 Markdown 给出解读。

Agent 只处理输入文本和模型输出，不依赖数据库或文件存储。
"""
from collections.abc import AsyncIterator
from pathlib import Path

from backend.agent.base_agent import BaseAgent

_PROMPT_FILE = Path(__file__).parent / "prompt" / "liuyao_analyst.txt"


class LiuYaoAnalyst(BaseAgent):
    """六爻解卦分析师"""

    def __init__(self):
        self._template = _PROMPT_FILE.read_text(encoding="utf-8")
        # 角色定义全在模板里；system prompt 留空
        super().__init__(name="liuyao_analyst", instructions="")

    async def interpret(self, markdown_content: str) -> str:
        """把排盘 Markdown 填入 prompt 模板并请求完整解读。"""
        user_prompt = self._template.format(
            paipan_markdown=markdown_content,
        )
        return await self.chat(user_prompt)

    async def interpret_stream(
        self,
        markdown_content: str,
    ) -> AsyncIterator[str]:
        """根据排盘 Markdown 逐段返回 Agent 解读文本。"""
        user_prompt = self._template.format(
            paipan_markdown=markdown_content,
        )
        async for chunk in self.chat_stream(user_prompt):
            yield chunk


# 模块级单例，避免每次请求都重新读 prompt 文件
analyst = LiuYaoAnalyst()
