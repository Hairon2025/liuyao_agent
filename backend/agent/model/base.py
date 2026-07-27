"""Chatbot 模型适配器基础接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from backend.schema.agent import ModelRequest, ModelStreamEvent


class ChatModelAdapter(ABC):
    """把具体模型 SDK 转换为内部标准流事件。

    适配器负责 SDK 参数和事件格式转换，不负责执行工具或管理 ReAct 循环。
    """

    @abstractmethod
    def stream(
        self,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        """执行一次模型调用并返回标准事件流。"""
        raise NotImplementedError
