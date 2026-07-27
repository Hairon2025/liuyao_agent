"""Chatbot 模型适配层。"""

from backend.agent.model.base import ChatModelAdapter
from backend.agent.model.openai_chat import (
    ModelAdapterProtocolError,
    OpenAIChatModelAdapter,
)

__all__ = [
    "ChatModelAdapter",
    "ModelAdapterProtocolError",
    "OpenAIChatModelAdapter",
]
