"""AI 工具表增加 body_type（HTTP 请求体类型）列

Revision ID: c7d22e1aa3f0
Revises: b6a11c0ffee2
Create Date: 2026-10-16 10:00:00.000000

说明：手写迁移。ai_tools 属插件模块表，**不由本迁移链创建**（由应用启动时补齐），
因此空库重放（如 SQLite 全链回归）时表可能尚不存在——存在才增列，保证可重放。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7d22e1aa3f0"
down_revision: str | None = "b6a11c0ffee2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def _has_column(table: str, column: str) -> bool:
        if not inspector.has_table(table):
            return False
        return column in {c["name"] for c in inspector.get_columns(table)}

    if inspector.has_table("ai_tools") and not _has_column("ai_tools", "body_type"):
        op.add_column(
            "ai_tools",
            sa.Column("body_type", sa.String(length=16), nullable=False, server_default="json",
                      comment="HTTP 请求体类型: none/json/form-data"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("ai_tools") and "body_type" in {
        c["name"] for c in inspector.get_columns("ai_tools")
    }:
        op.drop_column("ai_tools", "body_type")
