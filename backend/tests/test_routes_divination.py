"""divination 路由单元测试

覆盖 api/routes/divination.py 中的主要端点 + helper 函数：
- POST   /divinations                  — 4 种起卦方式 + 参数校验
- GET    /divinations                  — 列表
- GET    /divinations/{id}             — 查询（200 / 404）
- DELETE /divinations/{id}             — 删除（204 / 404）
- POST   /divinations/{id}/markdown    — 生成 Markdown
- GET    /divinations/{id}/markdown    — 读取 Markdown
- POST   /divinations/{id}/interpret/stream — SSE 流式解读
- _build_lines / _build_hexagram / _do_qigua (helper)

运行方式（在 backend/ 目录下）：
    pytest tests/test_routes_divination.py -v
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from backend.api.routes import divination as divination_routes
from backend.services.divination import _build_hexagram, _build_lines, _do_qigua


# ============================================================
# 1. POST /divinations — 4 种起卦方式 + 校验
# ============================================================


class TestCreateDivination:
    """POST /divinations"""

    # ----- manual -----

    def test_manual_qigua_success_returns_liweihuo(
        self, client: Any, created_divination_ids: list[str]
    ):
        """手动起卦 离为火 [2,1,2,2,1,2]，无动爻。"""
        resp = client.post(
            "/divinations",
            json={
                "method": "manual",
                "question": "测试手动起卦离为火",
                "numbers": [2, 1, 2, 2, 1, 2],
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        created_divination_ids.append(body["divination_id"])

        paipan = body["paipan"]
        assert paipan["ben_gua"]["name"] == "离为火"
        assert paipan["ben_gua"]["palace"] == "离宫"
        assert paipan["ben_gua"]["gua_type"] == "本宫卦"
        assert paipan["bian_gua"] is None
        assert paipan["moving_positions"] == []
        assert len(paipan["ben_gua"]["lines"]) == 6
        # 世爻 / 应爻
        assert paipan["ben_gua"]["shi_yao_position"] == 6
        assert paipan["ben_gua"]["ying_yao_position"] == 3
        # 干支
        assert set(paipan["ganzhi"].keys()) == {"year", "month", "day", "hour"}
        assert len(paipan["xunkong"]) == 2
        # 解读 (默认空 + 免责)
        assert body["interpretation"] is not None
        assert "娱乐参考" in body["interpretation"]["disclaimer"]
        # 不生成 markdown 时这两字段为 None
        assert body["markdown_path"] is None
        assert body["markdown_content"] is None

    def test_manual_qigua_with_moving_yao(
        self, client: Any, created_divination_ids: list[str]
    ):
        """手动起卦 火雷噬嗑初爻动 [3,1,1,2,1,2] → 变卦火地晋。"""
        resp = client.post(
            "/divinations",
            json={
                "method": "manual",
                "question": "测试动爻",
                "numbers": [3, 1, 1, 2, 1, 2],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        created_divination_ids.append(body["divination_id"])

        paipan = body["paipan"]
        assert paipan["ben_gua"]["name"] == "火雷噬嗑"
        assert paipan["bian_gua"] is not None
        assert paipan["bian_gua"]["name"] == "火地晋"
        assert paipan["moving_positions"] == [1]
        # 动爻爻位的 is_changing 应为 true
        moving_line = paipan["ben_gua"]["lines"][0]
        assert moving_line["position"] == 1
        assert moving_line["is_changing"] is True

    def test_manual_qigua_without_numbers_returns_400(self, client: Any):
        """manual 起卦未传 numbers → 400。"""
        resp = client.post(
            "/divinations",
            json={"method": "manual", "question": "缺 numbers"},
        )
        assert resp.status_code == 400
        assert "numbers" in resp.json()["detail"]

    # ----- coin -----

    def test_coin_qigua_returns_valid_hexagram(
        self, client: Any, created_divination_ids: list[str]
    ):
        """铜钱结果由前端投掷后传入，后端按六爻编码完成排盘。"""
        resp = client.post(
            "/divinations",
            json={
                "method": "coin",
                "question": "测试铜钱",
                "numbers": [2, 1, 2, 2, 1, 2],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        created_divination_ids.append(body["divination_id"])

        paipan = body["paipan"]
        # 必返回卦名（64 卦之一）
        assert paipan["ben_gua"]["name"]
        # 6 爻结构完整
        assert len(paipan["ben_gua"]["lines"]) == 6
        for line in paipan["ben_gua"]["lines"]:
            assert line["position"] in range(1, 7)
            assert line["line_type"] in ("少阴", "少阳", "纯阴", "纯阳")

    # ----- time -----

    def test_time_qigua_is_deterministic(
        self, client: Any, created_divination_ids: list[str]
    ):
        """时间起卦：固定时间应得到固定卦象（基于年+月+日+时辰的纯函数）。"""
        fixed_time = "2026-07-03T14:30:00"
        body1 = client.post(
            "/divinations",
            json={
                "method": "time",
                "question": "时间起卦测试 A",
                "time": fixed_time,
            },
        ).json()
        body2 = client.post(
            "/divinations",
            json={
                "method": "time",
                "question": "时间起卦测试 B",
                "time": fixed_time,
            },
        ).json()
        created_divination_ids.append(body1["divination_id"])
        created_divination_ids.append(body2["divination_id"])

        # 同一时间 = 同一卦
        assert body1["paipan"]["ben_gua"]["name"] == body2["paipan"]["ben_gua"]["name"]
        assert (
            body1["paipan"]["moving_positions"]
            == body2["paipan"]["moving_positions"]
        )

    # ----- random -----

    def test_random_qigua_returns_valid_hexagram(
        self, client: Any, created_divination_ids: list[str]
    ):
        """随机起卦：返回合法卦象。"""
        resp = client.post(
            "/divinations",
            json={"method": "random", "question": "测试随机"},
        )
        assert resp.status_code == 200
        body = resp.json()
        created_divination_ids.append(body["divination_id"])
        assert body["paipan"]["ben_gua"]["name"]

    # ----- generate_markdown -----

    def test_generate_markdown_true_populates_fields(
        self, client: Any, created_divination_ids: list[str]
    ):
        """generate_markdown=True 时响应含 Markdown 内容。"""
        resp = client.post(
            "/divinations",
            json={
                "method": "manual",
                "question": "生成 md 测试",
                "numbers": [2, 1, 2, 2, 1, 2],
                "generate_markdown": True,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        created_divination_ids.append(body["divination_id"])

        assert body["markdown_path"] is None
        assert body["markdown_content"] is not None
        assert "离为火" in body["markdown_content"]

    # ----- Pydantic 校验 -----

    def test_invalid_method_returns_422(self, client: Any):
        """无效 method → Pydantic 校验失败 422。"""
        resp = client.post(
            "/divinations",
            json={"method": "fake", "question": "x"},
        )
        assert resp.status_code == 422

    def test_empty_question_returns_422(self, client: Any):
        """question 为空字符串 → 422（min_length=1）。"""
        resp = client.post(
            "/divinations",
            json={"method": "manual", "question": "", "numbers": [2] * 6},
        )
        assert resp.status_code == 422

    def test_missing_question_returns_422(self, client: Any):
        """question 字段缺失 → 422。"""
        resp = client.post(
            "/divinations",
            json={"method": "manual", "numbers": [2] * 6},
        )
        assert resp.status_code == 422


# ============================================================
# 2. GET /divinations — 列表
# ============================================================


class TestListDivinations:
    """GET /divinations"""

    def test_list_returns_array_of_ids(self, client: Any):
        """列表返回字符串数组。"""
        resp = client.get("/divinations")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        # 已创建的解卦可能在列表里 (顺序未必固定)
        # 只校验类型 + 非空
        for div_id in resp.json():
            assert isinstance(div_id, str)
            assert len(div_id) > 0


# ============================================================
# 3. GET /divinations/{id} — 查询
# ============================================================


class TestGetDivination:
    """GET /divinations/{id}"""

    def _make(self, client, created_divination_ids):
        resp = client.post(
            "/divinations",
            json={
                "method": "manual",
                "question": "GET 测试",
                "numbers": [2, 1, 2, 2, 1, 2],
            },
        )
        body = resp.json()
        created_divination_ids.append(body["divination_id"])
        return body["divination_id"]

    def test_get_existing_returns_full_response(
        self, client: Any, created_divination_ids: list[str]
    ):
        """已存在的解卦 → 200，返回完整 DivinationResponse。"""
        div_id = self._make(client, created_divination_ids)
        resp = client.get(f"/divinations/{div_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["divination_id"] == div_id
        assert body["paipan"]["ben_gua"]["name"] == "离为火"
        # 与创建时响应一致
        assert body["interpretation"] is not None

    def test_get_nonexistent_returns_404(self, client: Any):
        """不存在的 ID → 404。"""
        resp = client.get("/divinations/nonexistent_id_xyz")
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]


# ============================================================
# 4. DELETE /divinations/{id}
# ============================================================


class TestDeleteDivination:
    """DELETE /divinations/{id}"""

    def test_delete_existing_returns_204_and_removes_record(
        self, client: Any, created_divination_ids: list[str]
    ):
        """删除已存在的解卦 → 204，且数据库记录确实被移除。"""
        # 先创建
        resp = client.post(
            "/divinations",
            json={
                "method": "manual",
                "question": "DELETE 测试",
                "numbers": [2, 1, 2, 2, 1, 2],
            },
        )
        div_id = resp.json()["divination_id"]
        # 不放进 created_divination_ids，因为我们手动验证删除

        # 删除
        del_resp = client.delete(f"/divinations/{div_id}")
        assert del_resp.status_code == 204

        # 数据库记录确实被移除
        assert client.get(f"/divinations/{div_id}").status_code == 404

    def test_delete_nonexistent_returns_404(self, client: Any):
        """删除不存在的 ID → 404。"""
        resp = client.delete("/divinations/nonexistent_id_xyz")
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]


# ============================================================
# 5. POST /divinations/{id}/markdown — 生成 Markdown
# ============================================================


class TestGenerateMarkdown:
    """POST /divinations/{id}/markdown"""

    def test_generate_markdown_returns_content(
        self, client: Any, created_divination_ids: list[str]
    ):
        """生成 Markdown → 200，并将内容保存到数据库。"""
        resp = client.post(
            "/divinations",
            json={
                "method": "manual",
                "question": "md 生成测试",
                "numbers": [2, 1, 2, 2, 1, 2],
            },
        )
        div_id = resp.json()["divination_id"]
        created_divination_ids.append(div_id)

        md_resp = client.post(f"/divinations/{div_id}/markdown")
        assert md_resp.status_code == 200
        body = md_resp.json()
        assert body["divination_id"] == div_id
        assert body["path"] is None
        assert "离为火" in body["content"]
        # 再次读取可证明内容已经持久化。
        saved = client.get(f"/divinations/{div_id}/markdown")
        assert saved.status_code == 200
        assert saved.json()["content"] == body["content"]

    def test_generate_markdown_for_nonexistent_returns_404(self, client: Any):
        """对不存在的解卦生成 md → 404。"""
        resp = client.post("/divinations/nonexistent_id_xyz/markdown")
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]


# ============================================================
# 6. GET /divinations/{id}/markdown — 读取
# ============================================================


class TestGetMarkdown:
    """GET /divinations/{id}/markdown"""

    def test_get_existing_markdown_returns_content(
        self, client: Any, created_divination_ids: list[str]
    ):
        """先 POST 生成，再 GET 读取 → 200。"""
        # 创建 + 生成 md
        resp = client.post(
            "/divinations",
            json={
                "method": "manual",
                "question": "GET md 测试",
                "numbers": [2, 1, 2, 2, 1, 2],
                "generate_markdown": True,
            },
        )
        div_id = resp.json()["divination_id"]
        created_divination_ids.append(div_id)

        # 读取
        md_resp = client.get(f"/divinations/{div_id}/markdown")
        assert md_resp.status_code == 200
        body = md_resp.json()
        assert body["divination_id"] == div_id
        assert "离为火" in body["content"]
        assert body["path"] is None

    def test_get_markdown_without_generating_returns_404(
        self, client: Any, created_divination_ids: list[str]
    ):
        """解卦存在但尚未生成 md → 404。"""
        # 创建（不生成 md）
        resp = client.post(
            "/divinations",
            json={
                "method": "manual",
                "question": "未生成 md 测试",
                "numbers": [2, 1, 2, 2, 1, 2],
            },
        )
        div_id = resp.json()["divination_id"]
        created_divination_ids.append(div_id)

        # 直接读
        md_resp = client.get(f"/divinations/{div_id}/markdown")
        assert md_resp.status_code == 404
        assert "请先调用" in md_resp.json()["detail"]

    def test_get_markdown_for_nonexistent_returns_404(self, client: Any):
        """不存在的解卦 → 404。"""
        resp = client.get("/divinations/nonexistent_id_xyz/markdown")
        assert resp.status_code == 404


# ============================================================
# 7. Agent 解读（非流式 + SSE 流式）
# ============================================================


class TestInterpretDivination:
    """POST /divinations/{id}/interpret"""

    def test_interpret_uses_database_markdown_and_persists_result(
        self,
        client: Any,
        created_divination_ids: list[str],
        monkeypatch: pytest.MonkeyPatch,
    ):
        created = client.post(
            "/divinations",
            json={
                "method": "manual",
                "question": "非流式解读测试",
                "numbers": [2, 1, 2, 2, 1, 2],
                "generate_markdown": True,
            },
        )
        divination_id = created.json()["divination_id"]
        created_divination_ids.append(divination_id)

        async def fake_interpret(markdown_content: str) -> str:
            assert "离为火" in markdown_content
            return "**数据库解读成功。**"

        monkeypatch.setattr(
            divination_routes.analyst,
            "interpret",
            fake_interpret,
        )

        response = client.post(f"/divinations/{divination_id}/interpret")

        assert response.status_code == 200
        assert (
            response.json()["interpretation"]["detail"]
            == "**数据库解读成功。**"
        )
        saved = client.get(f"/divinations/{divination_id}")
        assert (
            saved.json()["interpretation"]["detail"]
            == "**数据库解读成功。**"
        )


class TestInterpretDivinationStream:
    """POST /divinations/{id}/interpret/stream"""

    @staticmethod
    def _make_with_markdown(
        client: Any, created_divination_ids: list[str]
    ) -> str:
        resp = client.post(
            "/divinations",
            json={
                "method": "manual",
                "question": "SSE 流式解读测试",
                "numbers": [2, 1, 2, 2, 1, 2],
                "generate_markdown": True,
            },
        )
        assert resp.status_code == 200
        divination_id = resp.json()["divination_id"]
        created_divination_ids.append(divination_id)
        return divination_id

    def test_streams_multiline_chunks_and_persists_full_interpretation(
        self,
        client: Any,
        created_divination_ids: list[str],
        monkeypatch: pytest.MonkeyPatch,
    ):
        """文本逐块发送，正常完成后发送 [DONE] 并保存完整解读。"""
        divination_id = self._make_with_markdown(client, created_divination_ids)

        async def fake_interpret_stream(_: str):
            yield "# 总论\n"
            yield "**整体平稳。**"

        monkeypatch.setattr(
            divination_routes.analyst,
            "interpret_stream",
            fake_interpret_stream,
        )

        with client.stream(
            "POST", f"/divinations/{divination_id}/interpret/stream"
        ) as resp:
            body = "".join(resp.iter_text())

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert body == (
            "data: # 总论\n"
            "data: \n\n"
            "data: **整体平稳。**\n\n"
            "data: [DONE]\n\n"
        )

        saved = client.get(f"/divinations/{divination_id}")
        assert saved.status_code == 200
        assert (
            saved.json()["interpretation"]["detail"]
            == "# 总论\n**整体平稳。**"
        )

    def test_stream_failure_sends_error_without_done_or_partial_persistence(
        self,
        client: Any,
        created_divination_ids: list[str],
        monkeypatch: pytest.MonkeyPatch,
    ):
        """生成中途失败时发送错误消息，不发送 [DONE]，也不保存半截内容。"""
        divination_id = self._make_with_markdown(client, created_divination_ids)

        async def failing_interpret_stream(_: str):
            yield "已经生成的部分"
            raise RuntimeError("模型连接中断")

        monkeypatch.setattr(
            divination_routes.analyst,
            "interpret_stream",
            failing_interpret_stream,
        )

        with client.stream(
            "POST", f"/divinations/{divination_id}/interpret/stream"
        ) as resp:
            body = "".join(resp.iter_text())

        assert resp.status_code == 200
        assert "data: 已经生成的部分\n\n" in body
        assert "data: [ERROR]解卦失败：模型连接中断\n\n" in body
        assert "data: [DONE]\n\n" not in body

        saved = client.get(f"/divinations/{divination_id}")
        assert saved.status_code == 200
        assert saved.json()["interpretation"]["detail"] is None


# ============================================================
# 8. 用户归属与临时身份
# ============================================================


class TestDivinationOwnership:
    """所有卦例接口必须按 X-User-ID 隔离数据。"""

    def test_other_user_cannot_read_list_or_delete_record(
        self,
        client: Any,
    ):
        owner_id = client.headers["X-User-ID"]
        created = client.post(
            "/divinations",
            json={
                "method": "manual",
                "question": "用户隔离测试",
                "numbers": [2, 1, 2, 2, 1, 2],
            },
        )
        assert created.status_code == 200
        divination_id = created.json()["divination_id"]

        other_user = client.post("/users/guests", json={}).json()
        other_headers = {"X-User-ID": other_user["id"]}

        assert client.get(
            f"/divinations/{divination_id}",
            headers=other_headers,
        ).status_code == 404
        assert divination_id not in client.get(
            "/divinations",
            headers=other_headers,
        ).json()
        assert client.delete(
            f"/divinations/{divination_id}",
            headers=other_headers,
        ).status_code == 404

        # 非所有者的删除没有影响原始记录。
        owner_response = client.get(
            f"/divinations/{divination_id}",
            headers={"X-User-ID": owner_id},
        )
        assert owner_response.status_code == 200

    def test_missing_or_invalid_user_header_returns_401(self, client: Any):
        user_id = client.headers.pop("X-User-ID")
        try:
            assert client.get("/divinations").status_code == 401
            invalid = client.get(
                "/divinations",
                headers={"X-User-ID": "not-a-uuid"},
            )
            assert invalid.status_code == 401
        finally:
            client.headers["X-User-ID"] = user_id


# ============================================================
# 9. Helper functions
# ============================================================


class TestBuildLines:
    """_build_lines"""

    def test_builds_lineinfo_objects_from_dicts(self):
        lines_data = [
            {
                "position": 1, "liushen": "青龙", "liuqin": "兄弟",
                "line_type": "少阳", "symbol": "-----", "moving_mark": "   ",
                "tiangan": "甲", "dizhi": "子", "wuxing": "水",
                "shiying": "---", "is_changing": False, "score": 0.0,
                "status": [],
            },
        ]
        result = _build_lines(lines_data)
        assert len(result) == 1
        line = result[0]
        assert line.position == 1
        assert line.liushen == "青龙"
        assert line.tiangan == "甲"
        assert line.dizhi == "子"


class TestBuildHexagram:
    """_build_hexagram"""

    def test_builds_hexagram_with_all_fields(self):
        gua_data = {
            "palace": "乾宫",
            "gua_type": "本宫卦",
            "name": "乾为天",
            "guaci": "元亨利贞",
            "yaoci": ["初九：潜龙勿用"] * 6,
            "shi_yao_position": 6,
            "ying_yao_position": 3,
            "shi_yao_dizhi": "戌",
            "ying_yao_dizhi": "辰",
            "lines": [
                {
                    "position": i + 1, "liushen": "青龙", "liuqin": "兄弟",
                    "line_type": "少阳", "symbol": "-----", "moving_mark": "   ",
                    "tiangan": "甲", "dizhi": "子", "wuxing": "水",
                    "shiying": "世爻" if i == 5 else "应爻" if i == 2 else "---",
                    "is_changing": False, "score": 0.0, "status": [],
                }
                for i in range(6)
            ],
        }
        gua = _build_hexagram(gua_data)
        assert gua.name == "乾为天"
        assert gua.palace == "乾宫"
        assert len(gua.lines) == 6
        assert gua.shi_yao_position == 6


class TestDoQigua:
    """_do_qigua"""

    def test_manual_returns_numbers_as_is(self):
        req = _make_qigua_request(
            method="manual", numbers=[2, 1, 2, 2, 1, 2], time=datetime(2026, 7, 3, 14, 30)
        )
        lines, dt = _do_qigua(req)
        assert lines == [2, 1, 2, 2, 1, 2]
        assert dt == datetime(2026, 7, 3, 14, 30)

    def test_time_returns_deterministic_lines(self):
        """同一时间两次调用应得到相同卦象（纯函数）。"""
        req1 = _make_qigua_request(
            method="time", time=datetime(2026, 7, 3, 14, 30)
        )
        req2 = _make_qigua_request(
            method="time", time=datetime(2026, 7, 3, 14, 30)
        )
        lines1, _ = _do_qigua(req1)
        lines2, _ = _do_qigua(req2)
        assert lines1 == lines2
        # 6 爻皆为 1-4
        for n in lines1:
            assert n in (1, 2, 3, 4)

    def test_random_returns_six_valid_numbers(self):
        req = _make_qigua_request(method="random")
        lines, _ = _do_qigua(req)
        assert len(lines) == 6
        for n in lines:
            assert n in (1, 2, 3, 4)

    def test_coin_returns_six_valid_numbers(self):
        req = _make_qigua_request(
            method="coin",
            numbers=[2, 1, 2, 2, 1, 2],
        )
        lines, _ = _do_qigua(req)
        assert lines == [2, 1, 2, 2, 1, 2]


def _make_qigua_request(method: str, numbers=None, time=None):
    """构造 QiguaRequest（helper）。"""
    from backend.schema.api.divination import QiguaMethod, QiguaRequest

    return QiguaRequest(
        method=QiguaMethod(method),
        question="helper test",
        numbers=numbers,
        time=time,
    )
