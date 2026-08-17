"""为用户 LLM 设置增加追问建议开关。

Revision ID: 20260817_0010
Revises: 20260803_0009
Create Date: 2026-08-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260817_0010"
down_revision: Union[str, Sequence[str], None] = "20260803_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """现有用户默认保持开启，避免升级后功能状态突变。"""
    with op.batch_alter_table("user_llm_settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "suggestion_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("user_llm_settings") as batch_op:
        batch_op.drop_column("suggestion_enabled")
