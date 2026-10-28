"""AI 集成应用：增加「出口控制」channels 列

Revision ID: f3a4b5c6d7e8
Revises: e2a3b4c5d6e7
Create Date: 2026-10-28

说明：手写迁移。``ai_integration_apps`` 可由应用 create_all 兜底（新库已含该列），
此处 ``has_table`` + 查列幂等守卫，避免空库全链重放（SQLite 回归）失败。
channels 保存 ``{能力码: [rest,mcp]}``，用于按需授权时区分 REST / MCP 出口；
旧数据（无该列）一律为 NULL，读取时按「该能力全部支持出口」解释（向后兼容）。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: str | Sequence[str] | None = "e2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "ai_integration_apps" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("ai_integration_apps")}
    if "channels" in columns:
        return
    op.add_column(
        "ai_integration_apps",
        sa.Column(
            "channels",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="出口控制 {能力码: [rest,mcp]}，null=该能力全部支持出口",
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "ai_integration_apps" not in insp.get_table_names():
        return
    columns = {c["name"] for c in insp.get_columns("ai_integration_apps")}
    if "channels" in columns:
        op.drop_column("ai_integration_apps", "channels")
