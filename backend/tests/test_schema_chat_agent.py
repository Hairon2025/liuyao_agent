"""SDK 适配层使用的项目事件协议测试。"""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from backend.schema.agent import (
    ChatEvent,
    ChatEventType,
    ChatWorkflowState,
    ToolResult,
)


def test_tool_result_requires_consistent_error_state():
    success = ToolResult(
        success=True,
        model_content="已生成卦例。",
        data={"divination_id": "a" * 32},
    )
    assert success.error_code is None

    with pytest.raises(ValidationError, match="必须包含 error_code"):
        ToolResult(success=False, model_content="执行失败")


def test_chat_event_validates_sdk_adapter_output():
    delta = ChatEvent(
        event_type=ChatEventType.TEXT_DELTA,
        content="\n",
    )
    assert delta.content == "\n"

    result = ToolResult(success=True, model_content="工具执行完成。")
    completed = ChatEvent(
        event_type=ChatEventType.TOOL_CALL_COMPLETED,
        tool_call_id="call-1",
        tool_name="process_divination_request",
        tool_result=result,
    )
    assert completed.tool_result == result

    with pytest.raises(ValidationError, match="成功的 tool_result"):
        ChatEvent(
            event_type=ChatEventType.TOOL_CALL_COMPLETED,
            tool_call_id="call-2",
            tool_name="get_divination",
            tool_result=ToolResult(
                success=False,
                model_content="未找到",
                error_code="not_found",
            ),
        )

    suggestions = ChatEvent(
        event_type=ChatEventType.SUGGESTIONS,
        source_message_id=uuid.uuid4(),
        questions=["第一问", "第二问", "第三问"],
    )
    assert suggestions.questions == ["第一问", "第二问", "第三问"]

    with pytest.raises(ValidationError, match="三条追问"):
        ChatEvent(
            event_type=ChatEventType.SUGGESTIONS,
            source_message_id=uuid.uuid4(),
            questions=["只有一条"],
        )


def test_workflow_state_is_versioned_and_rejects_unknown_fields():
    state = ChatWorkflowState.model_validate(
        {
            "type": "divination",
            "version": 2,
            "status": "collecting",
            "payload": {
                "question": "工作发展",
                "method": "manual",
                "numbers": [1, 2, 1, 2, 1, 2],
            },
        }
    )
    assert state.payload.question == "工作发展"

    with pytest.raises(ValidationError, match="Extra inputs"):
        ChatWorkflowState.model_validate(
            {
                "payload": {},
                "model_can_control_user_id": "forbidden",
            }
        )
