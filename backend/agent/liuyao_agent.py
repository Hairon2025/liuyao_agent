"""六爻解卦分析师：根据已生成的排盘 Markdown 给出解读。

设计：
- prompt 文件是模板（含 {paipan_markdown} 占位符）
- 每次 interpret(divination_id) 时从 record + md 文件读出真实数据，str.format() 填进模板
- 填充后的整段文本作为 LLM 的 user 消息
"""
from collections.abc import AsyncIterator
from pathlib import Path

from backend.agent.base_agent import BaseAgent
from backend.running_data import divination_store

_PROMPT_FILE = Path(__file__).parent / "prompt" / "liuyao_analyst.txt"


class LiuYaoAnalyst(BaseAgent):
    """六爻解卦分析师"""

    def __init__(self):
        self._template = _PROMPT_FILE.read_text(encoding="utf-8")
        # 角色定义全在模板里；system prompt 留空
        super().__init__(name="liuyao_analyst", instructions="")

    async def interpret(self, divination_id: str) -> str:
        """读取 record + Markdown，把数据填进 prompt 模板，发给 LLM 解卦。

        Args:
            divination_id: 解卦 ID（对应 backend/running_data/divinations_{json,md}/{id}.{json,md}）

        Returns:
            LLM 生成的整篇 Markdown 解读

        Raises:
            FileNotFoundError: record 或 Markdown 不存在
        """

        md = divination_store.load_markdown(divination_id)
        if md is None:
            raise FileNotFoundError(
                f"未找到 {divination_id} 的 Markdown，请先调用 "
                f"POST /divinations/{divination_id}/markdown 生成"
            )

        # 嵌套：把 record 里的数据 + md 文件内容填进 prompt 模板
        user_prompt = self._template.format(
            paipan_markdown=md,
        )
        return await self.chat(user_prompt)

    async def interpret_stream(self, divination_id: str) -> AsyncIterator[str]:
        """读取排盘 Markdown，并逐段返回 Agent 解读文本。"""
        md = divination_store.load_markdown(divination_id)
        if md is None:
            raise FileNotFoundError(
                f"未找到 {divination_id} 的 Markdown，请先调用 "
                f"POST /divinations/{divination_id}/markdown 生成"
            )
        user_prompt = self._template.format(paipan_markdown=md)
        async for chunk in self.chat_stream(user_prompt):
            yield chunk


# 模块级单例，避免每次请求都重新读 prompt 文件
analyst = LiuYaoAnalyst()
