"""解卦相关路由"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import arrange_hexagram, cast_by_coin, cast_by_manual, cast_by_random, cast_by_time
from utils.markdown import to_markdown
from running_data import divination_store
from schema.api.divination import (
    DivinationResponse,
    InterpretationResult,
    LineInfo,
    HexagramInfo,
    PaipanResult,
    QiguaRequest,
)

router = APIRouter(prefix="/divinations", tags=["divination"])


class MarkdownResponse(BaseModel):
    """Markdown 生成响应"""
    divination_id: str
    path: str
    content: str


def _build_lines(lines_data: list[dict]) -> list[LineInfo]:
    return [LineInfo(**line) for line in lines_data]


def _build_hexagram(gua_data: dict) -> HexagramInfo:
    return HexagramInfo(
        palace=gua_data["palace"],
        gua_type=gua_data["gua_type"],
        name=gua_data["name"],
        guaci=gua_data.get("guaci", ""),
        yaoci=gua_data.get("yaoci", []),
        shi_yao_position=gua_data["shi_yao_position"],
        ying_yao_position=gua_data["ying_yao_position"],
        shi_yao_dizhi=gua_data["shi_yao_dizhi"],
        ying_yao_dizhi=gua_data["ying_yao_dizhi"],
        lines=_build_lines(gua_data["lines"]),
    )


def _do_qigua(req: QiguaRequest) -> tuple[list[int], datetime]:
    """根据起卦方式生成卦象编码和起卦时间。"""
    dt = req.time or datetime.now()

    if req.method.value == "manual":
        if not req.numbers:
            raise HTTPException(status_code=400, detail="manual 起卦需要提供 numbers")
        return cast_by_manual(req.numbers), dt

    if req.method.value == "coin":
        return cast_by_coin(), dt

    if req.method.value == "time":
        return cast_by_time(dt), dt

    if req.method.value == "random":
        return cast_by_random(), dt

    raise HTTPException(status_code=400, detail=f"未知起卦方式：{req.method}")


@router.post("", response_model=DivinationResponse)
async def create_divination(req: QiguaRequest):
    """创建一次解卦请求。

    业务流程：
    1. 起卦（core.qigua）
    2. 排盘（core.paipan）
    3. 落盘到 running_data/divinations_json/{id}.json
    4. 若 req.generate_markdown=True：渲染并落盘 Markdown，响应中带回内容
    5. 多 Agent 解卦（由 Agent 层处理，暂未接入）
    """
    lines, qigua_time = _do_qigua(req)
    divination_id = uuid.uuid4().hex[:8]

    try:
        result = arrange_hexagram(lines, qigua_time, req.question)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    paipan = PaipanResult(
        divination_id=divination_id,
        question=result["question"],
        qigua_time=datetime.fromisoformat(result["qigua_time"]),
        ganzhi=result["ganzhi"],
        xunkong=result["xunkong"],
        ben_gua=_build_hexagram(result["ben_gua"]),
        bian_gua=_build_hexagram(result["bian_gua"]) if result["bian_gua"] else None,
        moving_positions=result["moving_positions"],
    )

    response = DivinationResponse(
        divination_id=divination_id,
        paipan=paipan,
        interpretation=InterpretationResult(),  # 默认空解卦，由 Agent 填充
    )

    # 落盘 JSON
    divination_store.save(divination_id, response)

    # 按需一步生成 Markdown
    if req.generate_markdown:
        md_content = to_markdown(response)
        md_path = divination_store.save_markdown(divination_id, md_content)
        response.markdown_path = str(md_path)
        response.markdown_content = md_content

    return response


@router.get("", response_model=list[str])
async def list_divinations():
    """列出所有历史解卦 ID（按时间倒序）。"""
    return divination_store.list_all()


@router.get("/{divination_id}", response_model=DivinationResponse)
async def get_divination(divination_id: str):
    """根据 ID 查询解卦结果。"""
    response = divination_store.load(divination_id)
    if response is None:
        raise HTTPException(status_code=404, detail=f"解卦记录 {divination_id} 不存在")
    return response


@router.delete("/{divination_id}", status_code=204)
async def remove_divination(divination_id: str):
    """删除一次解卦记录（同时删除 JSON 与 Markdown 文件）。"""
    if not divination_store.delete(divination_id):
        raise HTTPException(status_code=404, detail=f"解卦记录 {divination_id} 不存在")


@router.post("/{divination_id}/markdown", response_model=MarkdownResponse)
async def generate_markdown(divination_id: str):
    """将指定 ID 的排盘结果渲染为格式化 Markdown 并落盘。

    - 读取 running_data/divinations_json/{id}.json
    - 调用 utils.markdown.to_markdown 渲染
    - 写入 running_data/divinations_md/{id}.md
    - 返回 Markdown 内容 + 落盘路径
    """
    response = divination_store.load(divination_id)
    if response is None:
        raise HTTPException(status_code=404, detail=f"解卦记录 {divination_id} 不存在")

    content = to_markdown(response)
    path = divination_store.save_markdown(divination_id, content)

    return MarkdownResponse(
        divination_id=divination_id,
        path=str(path),
        content=content,
    )


@router.get("/{divination_id}/markdown", response_model=MarkdownResponse)
async def get_markdown(divination_id: str):
    """读取已生成的 Markdown 文件（不重新生成）。"""
    content = divination_store.load_markdown(divination_id)
    if content is None:
        raise HTTPException(
            status_code=404,
            detail=f"Markdown 文件不存在，请先调用 POST /divinations/{divination_id}/markdown 生成",
        )
    path = divination_store.get_markdown_path(divination_id)
    return MarkdownResponse(
        divination_id=divination_id,
        path=str(path),
        content=content,
    )
