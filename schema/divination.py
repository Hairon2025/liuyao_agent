"""Pydantic 数据模型：起卦请求 / 解卦响应"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class QiguaMethod(str, Enum):
    """起卦方式"""
    MANUAL = "manual"
    COIN = "coin"
    TIME = "time"
    RANDOM = "random"


class QiguaRequest(BaseModel):
    """起卦请求"""
    method: QiguaMethod = Field(..., description="起卦方式")
    question: str = Field(..., min_length=1, description="所问事项")
    time: Optional[datetime] = None
    # 手动起卦
    numbers: Optional[List[int]] = None
    # 是否在排盘同时生成 Markdown 文件
    generate_markdown: bool = Field(
        default=False,
        description="是否同时生成格式化 Markdown 并落盘；为 true 时响应中会包含 markdown 字段",
    )


class LineInfo(BaseModel):
    """爻信息"""
    position: int = Field(..., ge=1, le=6, description="爻位（1=初爻，6=上爻）")
    liushen: str = Field(..., description="六神（青龙/朱雀/勾陈/螣蛇/白虎/玄武）")
    liuqin: str = Field(..., description="六亲（父母/兄弟/子孙/妻财/官鬼）")
    line_type: str = Field(..., description="爻类型（少阴/少阳/纯阴/纯阳）")
    symbol: str = Field(..., description="卦象符号（-- -- / -----）")
    moving_mark: str = Field(..., description="动爻标记")
    dizhi: str = Field(..., description="地支")
    wuxing: str = Field(..., description="五行")
    shiying: str = Field(..., description="世爻/应爻/---")
    is_changing: bool = Field(..., description="是否动爻")
    score: float = Field(..., description="旺衰得分")
    status: List[str] = Field(default_factory=list, description="状态列表")


class HexagramInfo(BaseModel):
    """卦象信息"""
    palace: str = Field(..., description="所属八宫")
    gua_type: str = Field(..., description="卦类型（本宫卦/一世卦/.../游魂/归魂）")
    name: str = Field(..., description="卦名")
    guaci: str = Field(..., description="卦辞")
    yaoci: List[str] = Field(..., description="六爻爻辞")
    shi_yao_position: int = Field(..., ge=1, le=6)
    ying_yao_position: int = Field(..., ge=1, le=6)
    shi_yao_dizhi: str
    ying_yao_dizhi: str
    lines: List[LineInfo] = Field(..., description="六爻详情")


class PaipanResult(BaseModel):
    """排盘结果"""
    divination_id: str = Field(..., description="解卦唯一 ID")
    question: str
    qigua_time: datetime
    ganzhi: dict = Field(..., description="年月日时地支")
    xunkong: List[str] = Field(..., description="旬空地支")
    ben_gua: HexagramInfo
    bian_gua: Optional[HexagramInfo] = None
    moving_positions: List[int] = Field(default_factory=list, description="动爻位置")


class InterpretationResult(BaseModel):
    """解卦结果（由 Agent 层填充）"""
    summary: Optional[str] = None
    detail: Optional[str] = None
    yongshen_analysis: Optional[str] = None
    dongbian_analysis: Optional[str] = None
    disclaimer: str = Field(
        default="本结果仅供文化娱乐参考，不构成任何人生决策依据。",
        description="免责声明",
    )


class DivinationResponse(BaseModel):
    """完整解卦响应"""
    divination_id: str
    paipan: PaipanResult
    interpretation: Optional[InterpretationResult] = None
    # 当请求中 generate_markdown=true 时填充
    markdown_path: Optional[str] = Field(
        default=None,
        description="Markdown 文件落盘路径（仅当 generate_markdown=true 时存在）",
    )
    markdown_content: Optional[str] = Field(
        default=None,
        description="Markdown 内容（仅当 generate_markdown=true 时存在）",
    )
