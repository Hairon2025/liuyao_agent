"""创建卦例表并关联用户。

Revision ID: 20260724_0002
Revises: 20260724_0001
Create Date: 2026-07-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260724_0002"
down_revision: Union[str, Sequence[str], None] = "20260724_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 divinations 表、用户外键和历史列表索引。"""
    op.create_table(
        "divinations",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("qigua_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("numbers", sa.JSON(), nullable=True),
        sa.Column("paipan", sa.JSON(), nullable=False),
        sa.Column("interpretation", sa.JSON(), nullable=True),
        sa.Column("markdown_content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_divinations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_divinations")),
    )
    op.create_index(
        op.f("ix_divinations_user_id"),
        "divinations",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_divinations_user_created_at",
        "divinations",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """删除卦例表。"""
    op.drop_index(
        "ix_divinations_user_created_at",
        table_name="divinations",
    )
    op.drop_index(
        op.f("ix_divinations_user_id"),
        table_name="divinations",
    )
    op.drop_table("divinations")
