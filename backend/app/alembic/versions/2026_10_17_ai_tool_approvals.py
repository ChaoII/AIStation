"""AI 用户危险工具授权表

Revision ID: c8d9e0f1a2b3
Revises: beef01cafe02
Create Date: 2026-10-17 09:00:00.000000

说明：手写迁移，与既有工作台迁移一致（autogenerate 会因影子表产生无关 DROP）。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: str | None = "beef01cafe02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "ai_tool_approvals" not in insp.get_table_names():
        op.create_table(
            "ai_tool_approvals",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("tool_name", sa.String(length=128), nullable=False),
            sa.Column("authorized", sa.Boolean(), nullable=True, default=True),
            sa.Column("status", sa.String(length=10), nullable=True, default="0"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_time", sa.DateTime(), nullable=True),
            sa.Column("updated_time", sa.DateTime(), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), nullable=True, default=False),
            sa.Column("deleted_time", sa.DateTime(), nullable=True),
            sa.Column("created_id", sa.Integer(), nullable=True),
            sa.Column("updated_id", sa.Integer(), nullable=True),
            sa.Column("deleted_id", sa.Integer(), nullable=True),
            sa.Column("uuid", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("ai_tool_approvals")
