"""卦例业务服务。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core import (
    arrange_hexagram,
    cast_by_manual,
    cast_by_random,
    cast_by_time,
)
from backend.models.divination import Divination
from backend.repositories.divination import DivinationRepository
from backend.schema.api.divination import (
    DivinationResponse,
    HexagramInfo,
    InterpretationResult,
    LineInfo,
    PaipanResult,
    QiguaRequest,
)
from backend.services.exceptions import (
    DivinationNotFoundError,
    MarkdownNotFoundError,
)
from backend.utils.markdown import to_markdown


def _build_lines(lines_data: list[dict]) -> list[LineInfo]:
    """把 core 层爻数据转换为 API Schema。"""
    return [LineInfo(**line) for line in lines_data]


def _build_hexagram(gua_data: dict) -> HexagramInfo:
    """把 core 层单卦数据转换为 API Schema。"""
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
    """根据请求生成卦象编码和起卦时间。

    该函数只抛出与 Web 框架无关的 ValueError，由路由统一转换状态码。
    """
    dt = req.time or datetime.now()

    if req.method.value in {"manual", "coin"}:
        if not req.numbers:
            raise ValueError("manual/coin 起卦需要提供 numbers")
        return cast_by_manual(req.numbers), dt

    if req.method.value == "time":
        return cast_by_time(dt), dt

    if req.method.value == "random":
        return cast_by_random(), dt

    raise ValueError(f"未知起卦方式：{req.method}")


class DivinationService:
    """编排起卦、排盘、Markdown 和数据库事务。"""

    def __init__(
        self,
        repository: DivinationRepository,
        session: AsyncSession,
    ):
        self._repository = repository
        self._session = session

    @staticmethod
    def _to_response(divination: Divination) -> DivinationResponse:
        """把数据库记录还原为现有 API 响应结构。"""
        interpretation = (
            InterpretationResult.model_validate(divination.interpretation)
            if divination.interpretation is not None
            else None
        )
        return DivinationResponse(
            divination_id=divination.id,
            paipan=PaipanResult.model_validate(divination.paipan),
            interpretation=interpretation,
            markdown_path=None,
            markdown_content=divination.markdown_content,
        )

    async def _get_model(
        self,
        divination_id: str,
        user_id: uuid.UUID,
    ) -> Divination:
        divination = await self._repository.get_for_user(
            divination_id,
            user_id,
        )
        if divination is None:
            # 对“不存在”和“不属于当前用户”统一返回未找到，避免泄露记录 ID。
            raise DivinationNotFoundError(divination_id)
        return divination

    async def create(
        self,
        request: QiguaRequest,
        user_id: uuid.UUID,
    ) -> DivinationResponse:
        """创建并持久化一条属于当前用户的卦例。"""
        lines, qigua_time = _do_qigua(request)
        divination_id = uuid.uuid4().hex
        result = arrange_hexagram(lines, qigua_time, request.question)

        paipan = PaipanResult(
            divination_id=divination_id,
            question=result["question"],
            qigua_time=datetime.fromisoformat(result["qigua_time"]),
            ganzhi=result["ganzhi"],
            xunkong=result["xunkong"],
            ben_gua=_build_hexagram(result["ben_gua"]),
            bian_gua=(
                _build_hexagram(result["bian_gua"])
                if result["bian_gua"]
                else None
            ),
            moving_positions=result["moving_positions"],
        )
        response = DivinationResponse(
            divination_id=divination_id,
            paipan=paipan,
            interpretation=InterpretationResult(),
        )

        if request.generate_markdown:
            response.markdown_content = to_markdown(response)

        divination = Divination(
            id=divination_id,
            user_id=user_id,
            method=request.method.value,
            question=paipan.question,
            qigua_time=paipan.qigua_time,
            numbers=request.numbers,
            paipan=paipan.model_dump(mode="json"),
            interpretation=(
                response.interpretation.model_dump(mode="json")
                if response.interpretation
                else None
            ),
            markdown_content=response.markdown_content,
        )
        await self._repository.add(divination)
        await self._session.commit()
        await self._session.refresh(divination)
        return self._to_response(divination)

    async def list_ids(self, user_id: uuid.UUID) -> list[str]:
        """列出当前用户的卦例 ID。"""
        rows = await self._repository.list_for_user(user_id)
        return [row.id for row in rows]

    async def get(
        self,
        divination_id: str,
        user_id: uuid.UUID,
    ) -> DivinationResponse:
        """读取当前用户的一条卦例。"""
        return self._to_response(
            await self._get_model(divination_id, user_id)
        )

    async def delete(
        self,
        divination_id: str,
        user_id: uuid.UUID,
    ) -> None:
        """删除当前用户的一条卦例。"""
        divination = await self._get_model(divination_id, user_id)
        await self._repository.delete(divination)
        await self._session.commit()

    async def generate_markdown(
        self,
        divination_id: str,
        user_id: uuid.UUID,
    ) -> str:
        """重新渲染 Markdown 并保存到数据库文本字段。"""
        divination = await self._get_model(divination_id, user_id)
        response = self._to_response(divination)
        content = to_markdown(response)
        await self._repository.update(
            divination,
            {"markdown_content": content},
        )
        await self._session.commit()
        return content

    async def get_markdown(
        self,
        divination_id: str,
        user_id: uuid.UUID,
    ) -> str:
        """读取已生成的 Markdown。"""
        divination = await self._get_model(divination_id, user_id)
        if divination.markdown_content is None:
            raise MarkdownNotFoundError(divination_id)
        return divination.markdown_content

    async def save_interpretation(
        self,
        divination_id: str,
        user_id: uuid.UUID,
        detail: str,
    ) -> DivinationResponse:
        """保存完整 AI 解读文本。"""
        divination = await self._get_model(divination_id, user_id)
        interpretation = InterpretationResult(detail=detail)
        await self._repository.update(
            divination,
            {"interpretation": interpretation.model_dump(mode="json")},
        )
        await self._session.commit()
        await self._session.refresh(divination)
        return self._to_response(divination)
