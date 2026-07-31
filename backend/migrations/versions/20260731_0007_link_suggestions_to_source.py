"""把追问建议与来源回答建立一对一关系。

Revision ID: 20260731_0007
Revises: 20260730_0006
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260731_0007"
down_revision: Union[str, Sequence[str], None] = "20260730_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加来源消息外键，并回填旧追问消息 payload 中的来源 ID。"""
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.add_column(
            sa.Column("source_message_id", sa.Uuid(), nullable=True)
        )
        batch_op.create_foreign_key(
            op.f("fk_chat_messages_source_message_id_chat_messages"),
            "chat_messages",
            ["source_message_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_chat_messages_source_message_id",
            ["source_message_id"],
        )

    # SQLite 的 json_extract 可直接读取历史 payload；无效或缺失值保持 NULL。
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            sa.text(
                "UPDATE chat_messages "
                "SET source_message_id = "
                "replace(json_extract(payload, '$.source_message_id'), '-', '') "
                "WHERE message_type = 'suggestions' "
                "AND json_valid(payload) "
                "AND json_extract(payload, '$.source_message_id') IS NOT NULL"
            )
        )


def downgrade() -> None:
    """移除来源消息关系，payload 中仍保留来源 ID。"""
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_constraint(
            "uq_chat_messages_source_message_id",
            type_="unique",
        )
        batch_op.drop_constraint(
            op.f("fk_chat_messages_source_message_id_chat_messages"),
            type_="foreignkey",
        )
        batch_op.drop_column("source_message_id")
