"""Chat 会话 API 测试。"""
from __future__ import annotations

from types import SimpleNamespace

from backend.agent.model import OpenAIChatModelAdapter


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

    other = client.post("/users/guests", json={}).json()["id"]
    original_user = client.headers["X-User-ID"]
    client.headers["X-User-ID"] = other
    assert client.get(f"/chat/sessions/{session_id}").status_code == 404
    client.headers["X-User-ID"] = original_user

    deleted = client.delete(f"/chat/sessions/{session_id}")
    assert deleted.status_code == 204
    assert client.get(f"/chat/sessions/{session_id}").status_code == 404


def test_stream_chat_message_persists_user_and_assistant(
    client,
    monkeypatch,
):
    class FakeCompletions:
        async def create(self, **kwargs):
            async def chunks():
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content="你好，",
                                tool_calls=None,
                            ),
                            finish_reason=None,
                        )
                    ]
                )
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content="可以继续问卦。",
                                tool_calls=None,
                            ),
                            finish_reason="stop",
                        )
                    ]
                )

            return chunks()

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )
    monkeypatch.setattr(
        OpenAIChatModelAdapter,
        "_get_client",
        lambda _: fake_client,
    )
    session_id = client.post(
        "/chat/sessions",
        json={},
    ).json()["id"]

    response = client.post(
        f"/chat/sessions/{session_id}/messages/stream",
        json={"message": "你好"},
    )

    assert response.status_code == 200
    assert "event: text_delta" in response.text
    assert "event: message_completed" in response.text
    assert "event: done" in response.text

    messages = client.get(
        f"/chat/sessions/{session_id}/messages?recent=true"
    ).json()
    assert [(item["role"], item["content"]) for item in messages] == [
        ("user", "你好"),
        ("assistant", "你好，可以继续问卦。"),
    ]


def test_stream_chat_message_executes_divination_tool_end_to_end(
    client,
    monkeypatch,
):
    class FakeCompletions:
        def __init__(self):
            self.call_count = 0

        async def create(self, **kwargs):
            self.call_count += 1

            async def first_step():
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content=None,
                                tool_calls=[
                                    SimpleNamespace(
                                        index=0,
                                        id="create-call",
                                        function=SimpleNamespace(
                                            name="create_divination",
                                            arguments=(
                                                '{"method":"random",'
                                                '"question":"工作机会"}'
                                            ),
                                        ),
                                    )
                                ],
                            ),
                            finish_reason="tool_calls",
                        )
                    ]
                )

            async def second_step():
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content="已经完成随机起卦。",
                                tool_calls=None,
                            ),
                            finish_reason="stop",
                        )
                    ]
                )

            return first_step() if self.call_count == 1 else second_step()

    completions = FakeCompletions()
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    monkeypatch.setattr(
        OpenAIChatModelAdapter,
        "_get_client",
        lambda _: fake_client,
    )
    session_id = client.post(
        "/chat/sessions",
        json={},
    ).json()["id"]

    response = client.post(
        f"/chat/sessions/{session_id}/messages/stream",
        json={"message": "帮我随机起一卦看工作机会"},
    )

    assert response.status_code == 200
    assert "event: tool_call_started" in response.text
    assert "event: tool_call_completed" in response.text
    session_data = client.get(
        f"/chat/sessions/{session_id}"
    ).json()
    divination_id = session_data["active_divination_id"]
    assert divination_id is not None
    assert client.get(f"/divinations/{divination_id}").status_code == 200

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
