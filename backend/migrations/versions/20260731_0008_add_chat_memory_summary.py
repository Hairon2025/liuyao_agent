"""为 Chatbot 增加 SDK Item 摘要边界。

Revision ID: 20260731_0008
Revises: 20260731_0007
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260731_0008"
down_revision: Union[str, Sequence[str], None] = "20260731_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加长期摘要覆盖的 SDK Item ID 与更新时间。"""
    # 第一批先保留 server_default，让 SQLite batch 重建表时能回填已有会话。
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "summary_through_agent_message_id",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "summary_updated_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )

    # 第二批再增加约束并移除仅用于迁移旧行的临时默认值。
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.create_check_constraint(
            op.f(
                "ck_chat_sessions_nonnegative_summary_agent_message_id"
            ),
            "summary_through_agent_message_id >= 0",
        )
        batch_op.alter_column(
            "summary_through_agent_message_id",
            server_default=None,
        )


def downgrade() -> None:
    """移除长期记忆摘要边界。"""
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.drop_constraint(
            op.f(
                "ck_chat_sessions_nonnegative_summary_agent_message_id"
            ),
            type_="check",
        )
        batch_op.drop_column("summary_updated_at")
        batch_op.drop_column("summary_through_agent_message_id")
