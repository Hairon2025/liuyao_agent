"""OpenAI Agents SDK 使用的六爻 Function Tools。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from agents import RunContextWrapper, function_tool

from backend.agent.runtime.context import AgentRunContext
from backend.schema.agent import ToolResult
from backend.schema.agent.workflow import CoinFace, DivinationTimeMode
from backend.schema.api.divination import QiguaMethod
from backend.services.exceptions import DivinationNotFoundError


def _tool_output(result: ToolResult) -> str:
    """SDK Function Tool 使用字符串传递稳定的结构化结果。"""
    return result.model_dump_json(exclude_none=True)


# DeepSeek 常规端点不启用 Beta strict mode；参数仍由 Python 工作流严格校验。
@function_tool(strict_mode=False)
async def process_divination_request(
    context: RunContextWrapper[AgentRunContext],
    method: Literal["manual", "coin", "time", "random"] | None = None,
    question: str | None = None,
    time_mode: DivinationTimeMode | None = None,
    time: datetime | None = None,
    numbers: list[int] | None = None,
    coin_tosses: list[list[CoinFace]] | None = None,
) -> str:
    """合并本轮已知起卦信息，缺失时返回待补字段，完整时自动起卦排盘。

    Args:
        method: 起卦方式；manual=手动、coin=铜钱、time=时间、random=随机。
        question: 用户本次所问事项。
        time_mode: now=真正起卦时使用当前时间；specified=使用指定时间。
        time: 用户指定的起卦时间，仅在 time_mode=specified 时传入。
        numbers: manual 的六个爻值，必须从初爻到上爻排列。
        coin_tosses: 本轮新增的铜钱结果；每次包含三个“字”或“花”，
            第一次投掷是初爻。可一次提交 1 到 6 次，后续调用会继续追加。
    """
    try:
        outcome = await context.context.chat_divination_workflow.process(
            user_id=context.context.user_id,
            session_id=context.context.session_id,
            question=question,
            method=QiguaMethod(method) if method is not None else None,
            time_mode=time_mode,
            time=time,
            numbers=numbers,
            coin_tosses=coin_tosses,
        )
    except ValueError as exc:
        return _tool_output(
            ToolResult(
                success=False,
                model_content=f"起卦参数不合法：{exc}",
                display_content="起卦参数需要修正",
                error_code="invalid_divination_arguments",
                retryable=True,
            )
        )

    data = outcome.model_dump(mode="json", exclude_none=True)
    if outcome.status == "needs_input":
        labels = {
            "question": "所问事项",
            "method": "起卦方式",
            "time_mode": "使用现在还是指定的起卦时间",
            "time": "具体起卦时间",
            "numbers": "从初爻到上爻的六个爻值",
            "coin_tosses": "尚未提供的铜钱投掷结果",
        }
        missing = "、".join(
            labels.get(item, item) for item in outcome.missing_fields
        )
        progress = ""
        if outcome.draft and outcome.draft.method == QiguaMethod.COIN:
            count = len(outcome.draft.coin_tosses)
            progress = (
                f"当前已记录 {count}/6 次；下一次是第 {count + 1} 次。"
                if count < 6
                else "六次投掷结果已记录完整。"
            )
        return _tool_output(
            ToolResult(
                success=True,
                model_content=(
                    f"起卦信息尚未完整，还需要：{missing}。{progress}"
                    "请向用户追问缺失信息，不要自行编造。"
                ),
                display_content=f"等待补充：{missing}",
                data=data,
            )
        )

    context.context.active_divination_id = outcome.divination_id
    context.context.workflow_state = None
    # 首次正式报告由 Python 编排器在工具运行结束后交给 LiuYaoAnalyst。
    # 不把完整 Markdown 再送回协调 Agent，避免重复解读与额外 Token 消耗。
    created_data = {
        "status": outcome.status,
        "divination_id": outcome.divination_id,
        "hexagram_name": outcome.hexagram_name,
        "qigua_time": (
            outcome.qigua_time.isoformat()
            if outcome.qigua_time is not None
            else None
        ),
    }
    return _tool_output(
        ToolResult(
            success=True,
            model_content=(
                f"已创建卦例 {outcome.divination_id}，"
                f"起卦时间为 {outcome.qigua_time}。"
                "首次正式解读将由专门的 LiuYaoAnalyst 生成；"
                "不要自行解读，也不要生成追问建议。"
            ),
            display_content=f"已完成排盘：{outcome.hexagram_name}",
            data=created_data,
        )
    )


@function_tool(strict_mode=False)
async def cancel_divination_request(
    context: RunContextWrapper[AgentRunContext],
) -> str:
    """取消当前尚未完成的起卦信息收集流程。

    已经完成并保存的卦例不会被删除，当前正在讨论的卦例也不会改变。
    """
    cancelled = await context.context.chat_divination_workflow.cancel(
        user_id=context.context.user_id,
        session_id=context.context.session_id,
    )
    context.context.workflow_state = None
    return _tool_output(
        ToolResult(
            success=True,
            model_content=(
                "已取消尚未完成的起卦流程。"
                if cancelled
                else "当前没有尚未完成的起卦流程。"
            ),
            display_content=(
                "已取消本次起卦"
                if cancelled
                else "没有待取消的起卦流程"
            ),
            data={"cancelled": cancelled},
        )
    )


@function_tool(strict_mode=False)
async def get_divination(
    context: RunContextWrapper[AgentRunContext],
    divination_id: str | None = None,
) -> str:
    """读取用户指定的卦例；未指定时读取当前会话正在讨论的卦例。

    Args:
        divination_id: 可选的 32 位卦例 ID。
    """
    target_id = divination_id or context.context.active_divination_id
    if target_id is None:
        return _tool_output(
            ToolResult(
                success=False,
                model_content="当前会话尚未关联卦例，请先起卦或提供卦例 ID。",
                error_code="active_divination_missing",
                retryable=True,
            )
        )
    try:
        response = await context.context.divination_service.get(
            target_id,
            context.context.user_id,
        )
        markdown = response.markdown_content
        if markdown is None:
            markdown = (
                await context.context.divination_service.generate_markdown(
                    target_id,
                    context.context.user_id,
                )
            )
    except DivinationNotFoundError:
        return _tool_output(
            ToolResult(
                success=False,
                model_content="卦例不存在或不属于当前用户。",
                error_code="divination_not_found",
                retryable=False,
            )
        )

    context.context.active_divination_id = target_id
    prior_interpretation = ""
    if response.interpretation and response.interpretation.detail:
        prior_interpretation = (
            "\n\n此前保存的 AI 解读：\n"
            f"{response.interpretation.detail}"
        )
    return _tool_output(
        ToolResult(
            success=True,
            model_content=(
                f"卦例 {target_id} 的真实排盘如下：\n"
                f"{markdown}{prior_interpretation}"
            ),
            display_content=f"已读取卦例：{response.paipan.ben_gua.name}",
            data={
                "divination_id": target_id,
                "question": response.paipan.question,
                "qigua_time": response.paipan.qigua_time.isoformat(),
            },
        )
    )


@function_tool(strict_mode=False)
async def list_divinations(
    context: RunContextWrapper[AgentRunContext],
    limit: int = 10,
) -> str:
    """列出当前用户最近的卦例。

    Args:
        limit: 返回数量，范围 1 到 20。
    """
    if limit < 1 or limit > 20:
        return _tool_output(
            ToolResult(
                success=False,
                model_content="limit 必须在 1 到 20 之间。",
                error_code="invalid_limit",
                retryable=True,
            )
        )
    records = await context.context.divination_service.list_summaries(
        context.context.user_id,
        limit=limit,
    )
    return _tool_output(
        ToolResult(
            success=True,
            model_content=(
                "用户最近的卦例如下：\n"
                + json.dumps(records, ensure_ascii=False)
            ),
            display_content=f"已读取 {len(records)} 条历史卦例",
            data=records,
        )
    )
