"""增加 Agents SDK 会话表与 Chatbot 工作流状态。

Revision ID: 20260728_0005
Revises: 20260724_0004
Create Date: 2026-07-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260728_0005"
down_revision: Union[str, Sequence[str], None] = "20260724_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 SDK Session 表，并为业务会话增加工作流草稿。"""
    op.create_table(
        "agent_sessions",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("message_data", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.session_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "idx_agent_messages_session_time",
        "agent_messages",
        ["session_id", "created_at"],
        unique=False,
    )
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("workflow_state", sa.JSON(), nullable=True)
        )


def downgrade() -> None:
    """移除 SDK Session 表与工作流草稿。"""
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.drop_column("workflow_state")
    op.drop_index(
        "idx_agent_messages_session_time",
        table_name="agent_messages",
    )
    op.drop_table("agent_messages")
    op.drop_table("agent_sessions")
