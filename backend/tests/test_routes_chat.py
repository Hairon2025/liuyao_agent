"""Chat 会话 API 与 SDK Runtime 边界测试。"""
from __future__ import annotations

from backend.agent.chatbot_agent import LiuYaoChatbot
from backend.agent.liuyao_agent import LiuYaoAnalyst
from backend.agent.suggested_question_agent import SuggestedQuestionAgent
from backend.schema.agent import (
    ChatEvent,
    ChatEventType,
    SuggestedQuestions,
    ToolResult,
)
from backend.schema.api.divination import QiguaMethod


def test_chat_session_crud_and_ownership(client):
    created = client.post(
        "/chat/sessions",
        json={"title": "工作卦"},
    )
    assert created.status_code == 201
    session_id = created.json()["id"]

    listed = client.get("/chat/sessions")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [session_id]

    renamed = client.patch(
        f"/chat/sessions/{session_id}",
        json={"title": "新的标题", "status": "archived"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "新的标题"
    assert client.patch(
        f"/chat/sessions/{session_id}",
        json={"status": None},
    ).status_code == 422

    blocked = client.post(
        f"/chat/sessions/{session_id}/messages/stream",
        json={"message": "继续分析"},
    )
    assert blocked.status_code == 409

    original_token = client.cookies.get("liuyao_session")
    client.cookies.delete("liuyao_session")
    client.post("/auth/guests", json={})
    assert client.get(f"/chat/sessions/{session_id}").status_code == 403
    client.cookies.set("liuyao_session", original_token)

    deleted = client.delete(f"/chat/sessions/{session_id}")
    assert deleted.status_code == 204
    assert client.get(f"/chat/sessions/{session_id}").status_code == 404


def test_stream_chat_message_persists_user_and_assistant(
    client,
    monkeypatch,
):
    async def fake_stream(self, **kwargs):
        assert kwargs["user_message"] == "你好"
        yield ChatEvent(
            event_type=ChatEventType.TEXT_DELTA,
            content="你好，",
        )
        yield ChatEvent(
            event_type=ChatEventType.TEXT_DELTA,
            content="可以继续问卦。",
        )
        yield ChatEvent(
            event_type=ChatEventType.MESSAGE_COMPLETED,
            content="你好，可以继续问卦。",
        )

    monkeypatch.setattr(LiuYaoChatbot, "stream", fake_stream)
    session_id = client.post("/chat/sessions", json={}).json()["id"]

    response = client.post(
        f"/chat/sessions/{session_id}/messages/stream",
        json={"message": "你好"},
    )

    assert response.status_code == 200
    assert "event: text_delta" in response.text
    assert "event: message_completed" in response.text
    assert '"message_id":' in response.text
    assert "event: done" in response.text

    messages = client.get(
        f"/chat/sessions/{session_id}/messages?recent=true"
    ).json()
    assert [(item["role"], item["content"]) for item in messages] == [
        ("user", "你好"),
        ("assistant", "你好，可以继续问卦。"),
    ]

    # 普通聊天没有卦例关联，后端直接返回空数组，不消耗追问模型 Token。
    suggestions = client.post(
        f"/chat/sessions/{session_id}/messages/"
        f"{messages[1]['id']}/suggestions"
    )
    assert suggestions.status_code == 200
    assert suggestions.json() == {
        "source_message_id": messages[1]["id"],
        "questions": [],
        "cached": False,
    }
    assert client.post(
        f"/chat/sessions/{session_id}/messages/"
        f"{messages[0]['id']}/suggestions"
    ).status_code == 409

    other_session_id = client.post("/chat/sessions", json={}).json()["id"]
    assert client.post(
        f"/chat/sessions/{other_session_id}/messages/"
        f"{messages[1]['id']}/suggestions"
    ).status_code == 404


def test_stream_chat_message_executes_fixed_workflow_end_to_end(
    client,
    monkeypatch,
):
    async def fake_stream(self, **kwargs):
        context = kwargs["context"]
        outcome = await context.chat_divination_workflow.process(
            user_id=context.user_id,
            session_id=context.session_id,
            method=QiguaMethod.RANDOM,
            question="工作机会",
        )
        context.active_divination_id = outcome.divination_id
        result = ToolResult(
            success=True,
            model_content=f"已完成排盘：{outcome.divination_id}",
            data={
                "status": "created",
                "divination_id": outcome.divination_id,
            },
        )
        yield ChatEvent(
            event_type=ChatEventType.TOOL_CALL_STARTED,
            tool_call_id="create-call",
            tool_name="process_divination_request",
            tool_arguments={
                "method": "random",
                "question": "工作机会",
            },
        )
        yield ChatEvent(
            event_type=ChatEventType.TOOL_CALL_COMPLETED,
            tool_call_id="create-call",
            tool_name="process_divination_request",
            tool_result=result,
        )
        yield ChatEvent(
            event_type=ChatEventType.MESSAGE_COMPLETED,
            content="已经完成随机起卦。",
        )

    monkeypatch.setattr(LiuYaoChatbot, "stream", fake_stream)

    async def fake_interpret_stream(self, markdown_content):
        assert "# 解卦记录" in markdown_content
        yield "这是首次"
        yield "正式解读。\n\n> 本结果仅供文化娱乐参考，不构成任何人生决策依据。"

    monkeypatch.setattr(
        LiuYaoAnalyst,
        "interpret_stream",
        fake_interpret_stream,
    )

    async def fake_suggestions(self, **kwargs):
        return SuggestedQuestions(
            questions=["怎么看用神？", "动爻有什么作用？", "应期如何判断？"]
        )

    monkeypatch.setattr(
        SuggestedQuestionAgent,
        "generate",
        fake_suggestions,
    )
    session_id = client.post("/chat/sessions", json={}).json()["id"]

    response = client.post(
        f"/chat/sessions/{session_id}/messages/stream",
        json={"message": "帮我随机起一卦看工作机会"},
    )

    assert response.status_code == 200
    assert "event: tool_call_started" in response.text
    assert "event: tool_call_completed" in response.text
    assert "event: suggestions" not in response.text
    session_data = client.get(f"/chat/sessions/{session_id}").json()
    divination_id = session_data["active_divination_id"]
    assert divination_id is not None
    divination = client.get(f"/divinations/{divination_id}")
    assert divination.status_code == 200
    assert (
        divination.json()["interpretation"]["detail"]
        == "这是首次正式解读。\n\n"
        "> 本结果仅供文化娱乐参考，不构成任何人生决策依据。"
    )

    messages = client.get(
        f"/chat/sessions/{session_id}/messages?recent=true"
    ).json()
    assert [item["message_type"] for item in messages] == [
        "text",
        "tool_call",
        "tool_result",
        "text",
    ]
    assert messages[2]["divination_id"] == divination_id
    assert messages[3]["content"].startswith("这是首次正式解读")

    suggestions = client.post(
        f"/chat/sessions/{session_id}/messages/"
        f"{messages[3]['id']}/suggestions"
    )
    assert suggestions.status_code == 200
    assert suggestions.json()["cached"] is False
    assert len(suggestions.json()["questions"]) == 3

    cached = client.post(
        f"/chat/sessions/{session_id}/messages/"
        f"{messages[3]['id']}/suggestions"
    )
    assert cached.status_code == 200
    assert cached.json()["cached"] is True

    messages = client.get(
        f"/chat/sessions/{session_id}/messages?recent=true"
    ).json()
    assert messages[-1]["message_type"] == "suggestions"
    assert messages[-1]["source_message_id"] == messages[-2]["id"]


def test_bound_divination_can_generate_first_interpretation(
    client,
    monkeypatch,
):
    divination = client.post(
        "/divinations",
        json={
            "method": "random",
            "question": "未来工作发展如何",
            "generate_markdown": True,
        },
    ).json()
    divination_id = divination["divination_id"]
    assert divination["interpretation"]["detail"] is None

    async def fake_stream(self, **kwargs):
        yield ChatEvent(
            event_type=ChatEventType.TOOL_CALL_STARTED,
            tool_call_id="interpret-existing",
            tool_name="request_initial_interpretation",
            tool_arguments={},
        )
        yield ChatEvent(
            event_type=ChatEventType.TOOL_CALL_COMPLETED,
            tool_call_id="interpret-existing",
            tool_name="request_initial_interpretation",
            tool_result=ToolResult(
                success=True,
                model_content="准备生成首次正式解读",
                data={
                    "status": "ready_for_interpretation",
                    "divination_id": divination_id,
                },
            ),
        )
        yield ChatEvent(
            event_type=ChatEventType.MESSAGE_COMPLETED,
            content="协调 Agent 的文本不应展示",
        )

    async def fake_interpret_stream(self, markdown_content):
        assert "未来工作发展如何" in markdown_content
        yield "已有排盘的首次正式解读。\n\n"
        yield "> 本结果仅供文化娱乐参考，不构成任何人生决策依据。"

    async def no_suggestions(self, **kwargs):
        return SuggestedQuestions(questions=[])

    monkeypatch.setattr(LiuYaoChatbot, "stream", fake_stream)
    monkeypatch.setattr(
        LiuYaoAnalyst,
        "interpret_stream",
        fake_interpret_stream,
    )
    monkeypatch.setattr(
        SuggestedQuestionAgent,
        "generate",
        no_suggestions,
    )

    session_id = client.post(
        "/chat/sessions",
        json={"active_divination_id": divination_id},
    ).json()["id"]
    response = client.post(
        f"/chat/sessions/{session_id}/messages/stream",
        json={"message": "请为当前卦例生成完整解读"},
    )

    assert response.status_code == 200
    assert '"tool_name":"request_initial_interpretation"' in response.text
    assert "已有排盘的首次正式解读" in response.text
    updated = client.get(f"/divinations/{divination_id}").json()
    assert updated["interpretation"]["detail"].startswith(
        "已有排盘的首次正式解读"
    )
    messages = client.get(
        f"/chat/sessions/{session_id}/messages?recent=true"
    ).json()
    assert [message["message_type"] for message in messages] == [
        "text",
        "tool_call",
        "tool_result",
        "text",
    ]
