"""增加正式认证、用户 LLM 设置与用量记录。

Revision ID: 20260803_0009
Revises: 20260731_0008
Create Date: 2026-08-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260803_0009"
down_revision: Union[str, Sequence[str], None] = "20260731_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """扩展用户身份，并创建认证、模型设置和用量表。"""
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("username", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "username_normalized",
                sa.String(length=32),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "last_login_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.create_index(
            op.f("ix_users_username_normalized"),
            ["username_normalized"],
            unique=True,
        )

    op.create_table(
        "user_credentials",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_credentials_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_credentials")),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
    )
    op.create_index(
        op.f("ix_auth_sessions_user_id"),
        "auth_sessions",
        ["user_id"],
    )
    op.create_index(
        op.f("ix_auth_sessions_token_hash"),
        "auth_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_auth_sessions_expires_at"),
        "auth_sessions",
        ["expires_at"],
    )

    op.create_table(
        "user_llm_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=False),
        sa.Column("api_key_last4", sa.String(length=4), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("analyst_model", sa.String(length=100), nullable=True),
        sa.Column("suggestion_model", sa.String(length=100), nullable=True),
        sa.Column("memory_model", sa.String(length=100), nullable=True),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_llm_settings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_llm_settings")),
    )
    op.create_index(
        op.f("ix_user_llm_settings_user_id"),
        "user_llm_settings",
        ["user_id"],
        unique=True,
    )

    op.create_table(
        "llm_usage_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("agent_role", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("base_url_host", sa.String(length=255), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('completed', 'failed', 'cancelled')",
            name=op.f("ck_llm_usage_records_valid_status"),
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name=op.f("ck_llm_usage_records_nonnegative_input_tokens"),
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name=op.f("ck_llm_usage_records_nonnegative_output_tokens"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_llm_usage_records_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_usage_records")),
    )
    op.create_index(
        op.f("ix_llm_usage_records_user_id"),
        "llm_usage_records",
        ["user_id"],
    )
    op.create_index(
        op.f("ix_llm_usage_records_agent_role"),
        "llm_usage_records",
        ["agent_role"],
    )
    op.create_index(
        op.f("ix_llm_usage_records_created_at"),
        "llm_usage_records",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_llm_usage_records_created_at"),
        table_name="llm_usage_records",
    )
    op.drop_index(
        op.f("ix_llm_usage_records_agent_role"),
        table_name="llm_usage_records",
    )
    op.drop_index(
        op.f("ix_llm_usage_records_user_id"),
        table_name="llm_usage_records",
    )
    op.drop_table("llm_usage_records")
    op.drop_index(
        op.f("ix_user_llm_settings_user_id"),
        table_name="user_llm_settings",
    )
    op.drop_table("user_llm_settings")
    op.drop_index(
        op.f("ix_auth_sessions_expires_at"),
        table_name="auth_sessions",
    )
    op.drop_index(
        op.f("ix_auth_sessions_token_hash"),
        table_name="auth_sessions",
    )
    op.drop_index(
        op.f("ix_auth_sessions_user_id"),
        table_name="auth_sessions",
    )
    op.drop_table("auth_sessions")
    op.drop_table("user_credentials")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index(op.f("ix_users_username_normalized"))
        batch_op.drop_column("last_login_at")
        batch_op.drop_column("username_normalized")
        batch_op.drop_column("username")
