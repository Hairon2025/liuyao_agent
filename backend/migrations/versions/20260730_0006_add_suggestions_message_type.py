"""允许 chat_messages 保存结构化追问建议。

Revision ID: 20260730_0006
Revises: 20260728_0005
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260730_0006"
down_revision: Union[str, Sequence[str], None] = "20260728_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_TYPES = "('text', 'tool_call', 'tool_result', 'summary')"
_NEW_TYPES = (
    "('text', 'tool_call', 'tool_result', 'summary', 'suggestions')"
)


def upgrade() -> None:
    """扩展消息类型检查约束。"""
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_chat_messages_valid_message_type"),
            type_="check",
        )
        batch_op.create_check_constraint(
            op.f("ck_chat_messages_valid_message_type"),
            f"message_type IN {_NEW_TYPES}",
        )


def downgrade() -> None:
    """恢复原消息类型；降级前不能存在 suggestions 消息。"""
    connection = op.get_bind()
    count = connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM chat_messages "
            "WHERE message_type = 'suggestions'"
        )
    )
    if count:
        raise RuntimeError(
            "chat_messages 中仍有 suggestions 消息，无法安全降级"
        )
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_chat_messages_valid_message_type"),
            type_="check",
        )
        batch_op.create_check_constraint(
            op.f("ck_chat_messages_valid_message_type"),
            f"message_type IN {_OLD_TYPES}",
        )
