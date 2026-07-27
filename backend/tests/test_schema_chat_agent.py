"""Chatbot Agent 内部协议测试。"""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from backend.schema.agent import (
    ChatContextMessage,
    ChatEvent,
    ChatEventType,
    ChatMessageType,
    ChatRole,
    ChatTurnInput,
    ToolContext,
    ToolResult,
)


def _text_message(sequence: int, content: str = "历史消息"):
    return ChatContextMessage(
        id=uuid.uuid4(),
        sequence=sequence,
        role=ChatRole.USER,
        content=content,
    )


def test_chat_turn_input_normalizes_text_and_accepts_incremental_context():
    """摘要和摘要后的消息可以组成一次完整 Agent 输入。"""
    turn_input = ChatTurnInput(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        user_message="  继续解释一下世爻  ",
        session_summary="  用户此前询问工作发展。  ",
        summary_through_sequence=2,
        recent_messages=[
            _text_message(3),
            _text_message(4, "最近一条消息"),
        ],
        active_divination_id="a" * 32,
        model="gpt-test",
    )

    assert turn_input.user_message == "继续解释一下世爻"
    assert turn_input.session_summary == "用户此前询问工作发展。"
    assert [item.sequence for item in turn_input.recent_messages] == [3, 4]
    assert turn_input.model_dump(mode="json")["user_id"] == str(
        turn_input.user_id
    )


@pytest.mark.parametrize(
    ("messages", "error_text"),
    [
        ([_text_message(2), _text_message(1)], "升序"),
        ([_text_message(1), _text_message(1)], "重复"),
    ],
)
def test_chat_turn_input_rejects_ambiguous_message_order(
    messages,
    error_text,
):
    with pytest.raises(ValidationError, match=error_text):
        ChatTurnInput(
            user_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            user_message="测试",
            recent_messages=messages,
        )


def test_chat_turn_input_rejects_messages_already_covered_by_summary():
    with pytest.raises(ValidationError, match="summary_through_sequence 之后"):
        ChatTurnInput(
            user_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            user_message="测试",
            session_summary="已经压缩",
            summary_through_sequence=3,
            recent_messages=[_text_message(3)],
        )


def test_chat_turn_input_requires_summary_when_cursor_is_advanced():
    with pytest.raises(ValidationError, match="必须提供 session_summary"):
        ChatTurnInput(
            user_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            user_message="测试",
            summary_through_sequence=2,
        )


def test_chat_turn_input_requires_cursor_when_summary_exists():
    with pytest.raises(ValidationError, match="必须大于 0"):
        ChatTurnInput(
            user_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            user_message="测试",
            session_summary="没有对应游标的摘要",
        )


def test_chat_context_message_validates_text_and_tool_pairing():
    with pytest.raises(ValidationError, match="非空 content"):
        _text_message(1, "   ")

    tool_message = ChatContextMessage(
        id=uuid.uuid4(),
        sequence=2,
        role=ChatRole.ASSISTANT,
        message_type=ChatMessageType.TOOL_CALL,
        tool_name="random_cast",
        tool_call_id="call-1",
        payload={"question": "工作发展"},
    )
    assert tool_message.tool_name == "random_cast"

    with pytest.raises(ValidationError, match="tool_name"):
        ChatContextMessage(
            id=uuid.uuid4(),
            sequence=3,
            role=ChatRole.TOOL,
            message_type=ChatMessageType.TOOL_RESULT,
            tool_call_id="call-1",
        )


def test_tool_context_rejects_model_controlled_extra_fields():
    context = ToolContext(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        tool_call_id="  call-1  ",
    )
    assert context.tool_call_id == "call-1"

    with pytest.raises(ValidationError, match="Extra inputs"):
        ToolContext(
            user_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            tool_call_id="call-1",
            injected_database_session="forbidden",
        )

    with pytest.raises(ValidationError, match="空白"):
        ToolContext(
            user_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            tool_call_id="   ",
        )


def test_tool_result_requires_consistent_success_and_error_state():
    success = ToolResult(
        success=True,
        model_content="已生成卦例。",
        display_content="起卦完成",
        data={"divination_id": "a" * 32},
    )
    assert success.error_code is None

    failure = ToolResult(
        success=False,
        model_content="起卦参数不完整。",
        error_code="invalid_arguments",
        retryable=False,
    )
    assert failure.success is False

    with pytest.raises(ValidationError, match="不能包含 error_code"):
        ToolResult(
            success=True,
            model_content="成功",
            error_code="unexpected",
        )

    with pytest.raises(ValidationError, match="必须包含 error_code"):
        ToolResult(
            success=False,
            model_content="执行失败",
        )


def test_chat_event_validates_each_observable_event_shape():
    # 纯换行也是合法的 Markdown 文本增量，不能被当作空事件丢弃。
    delta = ChatEvent(
        event_type=ChatEventType.TEXT_DELTA,
        content="\n",
    )
    assert delta.content == "\n"

    started = ChatEvent(
        event_type=ChatEventType.TOOL_CALL_STARTED,
        tool_call_id="call-1",
        tool_name="random_cast",
        tool_arguments={"question": "工作发展"},
    )
    assert started.tool_arguments == {"question": "工作发展"}

    completed = ChatEvent(
        event_type=ChatEventType.TOOL_CALL_COMPLETED,
        tool_call_id="call-1",
        tool_name="random_cast",
        tool_result=ToolResult(
            success=True,
            model_content="工具执行完成。",
        ),
    )
    assert completed.tool_result is not None
    assert completed.tool_result.success is True

    failed = ChatEvent(
        event_type=ChatEventType.TOOL_CALL_FAILED,
        tool_call_id="call-2",
        tool_name="time_cast",
        tool_result=ToolResult(
            success=False,
            model_content="缺少起卦时间。",
            error_code="missing_time",
        ),
    )
    assert failed.tool_result is not None
    assert failed.tool_result.error_code == "missing_time"

    final = ChatEvent(
        event_type=ChatEventType.MESSAGE_COMPLETED,
        content="这是最终回答。",
    )
    assert final.content == "这是最终回答。"

    error = ChatEvent(
        event_type=ChatEventType.ERROR,
        content="Agent 执行超时。",
        error_code="agent_timeout",
        retryable=True,
    )
    assert error.retryable is True

    with pytest.raises(ValidationError, match="空白"):
        ChatEvent(
            event_type=ChatEventType.TOOL_CALL_STARTED,
            tool_call_id="call-3",
            tool_name="   ",
        )


@pytest.mark.parametrize(
    "event",
    [
        {"event_type": "text_delta"},
        {
            "event_type": "tool_call_started",
            "tool_call_id": "call-1",
        },
        {
            "event_type": "tool_call_completed",
            "tool_call_id": "call-1",
            "tool_name": "random_cast",
        },
        {
            "event_type": "tool_call_failed",
            "tool_call_id": "call-1",
            "tool_name": "random_cast",
            "tool_result": {
                "success": True,
                "model_content": "错误的成功状态",
            },
        },
        {
            "event_type": "error",
            "content": "没有错误代码",
        },
    ],
)
def test_chat_event_rejects_incomplete_payload(event):
    with pytest.raises(ValidationError):
        ChatEvent.model_validate(event)
