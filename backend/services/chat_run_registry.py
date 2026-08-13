"""单进程 Chat Agent Run 登记与显式取消。

当前部署仍是单实例，使用进程内注册表即可让取消请求找到正在执行的 SSE 任务。
未来多实例部署时，这一边界可以替换为 Redis 锁与取消信号，而不改 API 协议。
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Literal


CancelState = Literal["cancelled", "cancelling", "already_finished"]


class ChatRunConflictError(Exception):
    """同一会话已经有一轮回答正在执行。"""


@dataclass
class _RunHandle:
    request_id: uuid.UUID
    session_id: uuid.UUID
    user_id: uuid.UUID
    task: asyncio.Task[object] | None = None
    cancel_requested: bool = False
    finished: asyncio.Event = field(default_factory=asyncio.Event)


class ChatRunRegistry:
    """保存当前进程内正在运行的 Chat 请求。"""

    def __init__(self) -> None:
        self._by_request: dict[uuid.UUID, _RunHandle] = {}
        self._by_session: dict[uuid.UUID, uuid.UUID] = {}
        self._lock = asyncio.Lock()

    async def prepare(
        self,
        *,
        request_id: uuid.UUID,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """在返回 SSE 响应前预登记，避免早到的取消请求丢失。"""
        async with self._lock:
            active_request = self._by_session.get(session_id)
            if active_request is not None or request_id in self._by_request:
                raise ChatRunConflictError(str(active_request))
            handle = _RunHandle(
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
            )
            self._by_request[request_id] = handle
            self._by_session[session_id] = request_id

    async def is_prepared(self, request_id: uuid.UUID) -> bool:
        """判断请求是否已经由 API 层预登记。"""
        async with self._lock:
            return request_id in self._by_request

    async def activate(self, request_id: uuid.UUID) -> None:
        """用户消息落库后绑定当前流任务，并响应可能提前到达的取消。"""
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("无法取得当前 Chat Run 任务")
        async with self._lock:
            handle = self._by_request.get(request_id)
            if handle is None:
                raise RuntimeError("Chat Run 尚未登记或已经结束")
            handle.task = task
            cancel_requested = handle.cancel_requested
        if cancel_requested:
            task.cancel()

    async def cancel(
        self,
        *,
        request_id: uuid.UUID,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        wait_seconds: float = 5.0,
    ) -> CancelState:
        """请求取消并等待流任务完成取消持久化。"""
        async with self._lock:
            handle = self._by_request.get(request_id)
            if (
                handle is None
                or handle.session_id != session_id
                or handle.user_id != user_id
            ):
                return "already_finished"
            handle.cancel_requested = True
            task = handle.task
            finished = handle.finished
        if task is not None and not task.done():
            task.cancel()
        try:
            await asyncio.wait_for(finished.wait(), timeout=wait_seconds)
        except TimeoutError:
            return "cancelling"
        return "cancelled"

    async def finish(self, request_id: uuid.UUID) -> None:
        """释放会话运行槽，并唤醒等待取消完成的请求。"""
        async with self._lock:
            handle = self._by_request.pop(request_id, None)
            if handle is None:
                return
            if self._by_session.get(handle.session_id) == request_id:
                self._by_session.pop(handle.session_id, None)
            handle.finished.set()


chat_run_registry = ChatRunRegistry()
