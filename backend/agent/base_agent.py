"""基础 Agent 抽象（OpenAI Agents SDK 风格）

所有具体角色 Agent 都继承本类，在 __init__ 中提供 name / instructions / model，
并通过 chat(user_input) 调用 LLM。
"""
import os

from backend.config.settings import settings
from agents import Agent, Runner, set_default_openai_api, set_tracing_disabled

# 将 settings 中的 LLM 配置映射到 openai-agents SDK 期望的 env var
# 用 setdefault，shell 里实际设过的 OPENAI_API_KEY / OPENAI_BASE_URL 优先
os.environ.setdefault("OPENAI_API_KEY", settings.llm_api_key)
os.environ.setdefault("OPENAI_BASE_URL", settings.llm_base_url)

set_default_openai_api("chat_completions")
set_tracing_disabled(True)


class BaseAgent:
    """基础角色代理类"""

    def __init__(self, name: str, instructions: str, model: str | None = None):
        self.name = name
        self.agent = Agent(
            name=name,
            model=model or settings.llm_model,
            instructions=instructions,
        )

    async def chat(self, user_input: str) -> str:
        """运行 agent，返回模型回复文本。"""
        result = await Runner.run(self.agent, user_input)
        return result.final_output
