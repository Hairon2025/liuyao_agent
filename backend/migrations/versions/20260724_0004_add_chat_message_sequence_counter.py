"""为聊天会话增加消息序号计数器。

Revision ID: 20260724_0004
Revises: 20260724_0003
Create Date: 2026-07-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260724_0004"
down_revision: Union[str, Sequence[str], None] = "20260724_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加可被 Repository 原子递增的 next_message_sequence。"""
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "next_message_sequence",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            )
        )
        batch_op.create_check_constraint(
            "ck_chat_sessions_positive_next_message_sequence",
            "next_message_sequence > 0",
        )
        # 默认值只用于兼容可能已存在的会话，后续由 ORM 显式初始化。
        batch_op.alter_column(
            "next_message_sequence",
            server_default=None,
        )


def downgrade() -> None:
    """移除消息序号计数器。"""
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.drop_constraint(
            "ck_chat_sessions_positive_next_message_sequence",
            type_="check",
        )
        batch_op.drop_column("next_message_sequence")
