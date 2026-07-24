"""创建最小用户表。

Revision ID: 20260724_0001
Revises:
Create Date: 2026-07-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260724_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 users 表及常用索引。"""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_type", sa.String(length=20), nullable=False),
        sa.Column("display_name", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "user_type IN ('guest', 'registered')",
            name=op.f("ck_users_valid_user_type"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(
        op.f("ix_users_user_type"),
        "users",
        ["user_type"],
        unique=False,
    )


def downgrade() -> None:
    """删除 users 表。"""
    op.drop_index(op.f("ix_users_user_type"), table_name="users")
    op.drop_table("users")
