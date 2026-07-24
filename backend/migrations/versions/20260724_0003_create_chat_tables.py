"""创建聊天会话和消息表。

Revision ID: 20260724_0003
Revises: 20260724_0002
Create Date: 2026-07-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260724_0003"
down_revision: Union[str, Sequence[str], None] = "20260724_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 chat_sessions 和 chat_messages。"""
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "active_divination_id",
            sa.String(length=32),
            nullable=True,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "summary_through_sequence",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name=op.f("ck_chat_sessions_valid_status"),
        ),
        sa.CheckConstraint(
            "summary_through_sequence >= 0",
            name=op.f("ck_chat_sessions_nonnegative_summary_sequence"),
        ),
        sa.ForeignKeyConstraint(
            ["active_divination_id"],
            ["divinations.id"],
            name=op.f(
                "fk_chat_sessions_active_divination_id_divinations"
            ),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_chat_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_sessions")),
    )
    op.create_index(
        op.f("ix_chat_sessions_active_divination_id"),
        "chat_sessions",
        ["active_divination_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chat_sessions_user_id"),
        "chat_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_sessions_user_last_message_at",
        "chat_sessions",
        ["user_id", "last_message_at"],
        unique=False,
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("divination_id", sa.String(length=32), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("message_type", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.String(length=100), nullable=True),
        sa.Column("tool_call_id", sa.String(length=100), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "message_type IN "
            "('text', 'tool_call', 'tool_result', 'summary')",
            name=op.f("ck_chat_messages_valid_message_type"),
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name=op.f("ck_chat_messages_valid_role"),
        ),
        sa.CheckConstraint(
            "sequence > 0",
            name=op.f("ck_chat_messages_positive_sequence"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed', 'cancelled')",
            name=op.f("ck_chat_messages_valid_status"),
        ),
        sa.CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name=op.f("ck_chat_messages_nonnegative_token_count"),
        ),
        sa.ForeignKeyConstraint(
            ["divination_id"],
            ["divinations.id"],
            name=op.f("fk_chat_messages_divination_id_divinations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_sessions.id"],
            name=op.f("fk_chat_messages_session_id_chat_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_messages")),
        sa.UniqueConstraint(
            "session_id",
            "sequence",
            name="uq_chat_messages_session_sequence",
        ),
    )
    op.create_index(
        op.f("ix_chat_messages_divination_id"),
        "chat_messages",
        ["divination_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chat_messages_tool_call_id"),
        "chat_messages",
        ["tool_call_id"],
        unique=False,
    )


def downgrade() -> None:
    """按依赖关系逆序删除聊天表。"""
    op.drop_index(
        op.f("ix_chat_messages_tool_call_id"),
        table_name="chat_messages",
    )
    op.drop_index(
        op.f("ix_chat_messages_divination_id"),
        table_name="chat_messages",
    )
    op.drop_table("chat_messages")

    op.drop_index(
        "ix_chat_sessions_user_last_message_at",
        table_name="chat_sessions",
    )
    op.drop_index(
        op.f("ix_chat_sessions_user_id"),
        table_name="chat_sessions",
    )
    op.drop_index(
        op.f("ix_chat_sessions_active_divination_id"),
        table_name="chat_sessions",
    )
    op.drop_table("chat_sessions")
