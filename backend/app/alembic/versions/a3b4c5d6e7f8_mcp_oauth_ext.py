"""AI 集成开放平台：ai_mcp_servers 增列 oauth_ext_service_id（绑定外部OAuth服务）

Revision ID: a3b4c5d6e7f8
Revises: b8c9d0e1f2a3
Create Date: 2026-10-29 18:00:00.000000

说明：手写迁移（autogenerate 会因本项目大量历史/影子表产生无关 DROP）。
仅追加一列 + 索引，用 ``has_column`` 幂等守卫，避免空库全链重放（SQLite 回归）失败。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "ai_mcp_servers" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("ai_mcp_servers")}
        if "oauth_ext_service_id" not in cols:
            op.add_column(
                "ai_mcp_servers",
                sa.Column("oauth_ext_service_id", sa.Integer(), nullable=True, comment="绑定的外部OAuth服务ID（MCP建连时注入Bearer）"),
            )
            op.create_index(op.f("ix_ai_mcp_servers_oauth_ext_service_id"), "ai_mcp_servers", ["oauth_ext_service_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "ai_mcp_servers" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("ai_mcp_servers")}
        if "oauth_ext_service_id" in cols:
            op.drop_index(op.f("ix_ai_mcp_servers_oauth_ext_service_id"), table_name="ai_mcp_servers")
            op.drop_column("ai_mcp_servers", "oauth_ext_service_id")
