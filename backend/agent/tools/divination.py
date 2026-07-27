"""供 Chatbot ReActRunner 使用的六爻业务工具。"""
from __future__ import annotations

import json

from backend.agent.tools.base import AgentTool
from backend.schema.agent import ToolContext, ToolResult
from backend.schema.agent.divination_tool import (
    CreateDivinationArguments,
    GetDivinationArguments,
    ListDivinationsArguments,
)
from backend.schema.api.divination import QiguaRequest
from backend.services.divination import DivinationService
from backend.services.exceptions import DivinationNotFoundError


class CreateDivinationTool(AgentTool[CreateDivinationArguments]):
    """按用户给出的方式起卦、排盘并持久化。"""

    def __init__(self, service: DivinationService):
        super().__init__(
            name="create_divination",
            description=(
                "创建一条六爻卦例并完成排盘。支持 manual、coin、time、"
                "random；manual/coin 的 numbers 必须按初爻到上爻排列。"
            ),
            arguments_schema=CreateDivinationArguments,
        )
        self._service = service

    async def execute(
        self,
        context: ToolContext,
        arguments: CreateDivinationArguments,
    ) -> ToolResult:
        response = await self._service.create(
            QiguaRequest(
                method=arguments.method,
                question=arguments.question,
                time=arguments.time,
                numbers=arguments.numbers,
                generate_markdown=True,
            ),
            context.user_id,
        )
        markdown = response.markdown_content or ""
        return ToolResult(
            success=True,
            model_content=(
                f"已创建卦例 {response.divination_id}。以下为真实排盘：\n"
                f"{markdown}"
            ),
            display_content=f"已完成排盘：{response.paipan.ben_gua.name}",
            data={
                "divination_id": response.divination_id,
                "method": arguments.method,
                "question": response.paipan.question,
                "qigua_time": response.paipan.qigua_time.isoformat(),
            },
        )


class GetDivinationTool(AgentTool[GetDivinationArguments]):
    """读取指定卦例，未指定时读取会话当前卦例。"""

    def __init__(self, service: DivinationService):
        super().__init__(
            name="get_divination",
            description=(
                "读取用户已有卦例的完整排盘，供继续解读。未提供 "
                "divination_id 时读取当前会话正在讨论的卦例。"
            ),
            arguments_schema=GetDivinationArguments,
        )
        self._service = service

    async def execute(
        self,
        context: ToolContext,
        arguments: GetDivinationArguments,
    ) -> ToolResult:
        divination_id = (
            arguments.divination_id or context.active_divination_id
        )
        if divination_id is None:
            return ToolResult(
                success=False,
                model_content=(
                    "当前会话尚未关联卦例，请让用户提供卦例 ID，"
                    "或先调用 create_divination。"
                ),
                error_code="active_divination_missing",
                retryable=True,
            )

        try:
            response = await self._service.get(
                divination_id,
                context.user_id,
            )
            markdown = response.markdown_content
            if markdown is None:
                markdown = await self._service.generate_markdown(
                    divination_id,
                    context.user_id,
                )
        except DivinationNotFoundError:
            return ToolResult(
                success=False,
                model_content="卦例不存在或不属于当前用户。",
                error_code="divination_not_found",
                retryable=False,
            )

        prior_interpretation = ""
        if response.interpretation and response.interpretation.detail:
            prior_interpretation = (
                "\n\n此前保存的 AI 解读：\n"
                f"{response.interpretation.detail}"
            )
        return ToolResult(
            success=True,
            model_content=(
                f"卦例 {divination_id} 的真实排盘如下：\n"
                f"{markdown}{prior_interpretation}"
            ),
            display_content=f"已读取卦例：{response.paipan.ben_gua.name}",
            data={
                "divination_id": divination_id,
                "question": response.paipan.question,
                "qigua_time": response.paipan.qigua_time.isoformat(),
            },
        )


class ListDivinationsTool(AgentTool[ListDivinationsArguments]):
    """列出当前用户最近的卦例。"""

    def __init__(self, service: DivinationService):
        super().__init__(
            name="list_divinations",
            description="列出当前用户最近的卦例 ID、问题、时间和本卦名。",
            arguments_schema=ListDivinationsArguments,
        )
        self._service = service

    async def execute(
        self,
        context: ToolContext,
        arguments: ListDivinationsArguments,
    ) -> ToolResult:
        records = await self._service.list_summaries(
            context.user_id,
            limit=arguments.limit,
        )
        return ToolResult(
            success=True,
            model_content=(
                "用户最近的卦例如下：\n"
                + json.dumps(records, ensure_ascii=False)
            ),
            display_content=f"已读取 {len(records)} 条历史卦例",
            data=records,
        )
