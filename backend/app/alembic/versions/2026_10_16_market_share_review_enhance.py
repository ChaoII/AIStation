"""分享与审核增强：ai_market_shares 支持分享个人资产

Revision ID: d3f4a5b6c789
Revises: c7d22e1aa3f0
Create Date: 2026-10-16 09:00:00.000000

说明：手写迁移。autogenerate 会因本项目数据库存在大量未被模型覆盖的
历史/影子表（ont_* 等）产生无关 DROP，因此只保留本次特性所需变更。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.alembic.dialect_compat import is_sqlite

# revision identifiers, used by Alembic.
revision: str = "d3f4a5b6c789"
down_revision: str | None = "c7d22e1aa3f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _alter_item_id_nullable(nullable: bool) -> None:
    """跨方言改 ``item_id`` 可空性。

    ⚠️ SQLite **不支持** ``ALTER COLUMN ... DROP/SET NOT NULL``，必须走
    ``batch_alter_table``（重建表）；否则空库全链重放（SQLite 回归）会以
    ``near "ALTER": syntax error`` 直接失败。
    """
    if is_sqlite(op.get_bind()):
        with op.batch_alter_table("ai_market_shares") as batch_op:
            batch_op.alter_column(
                "item_id", existing_type=sa.Integer(), nullable=nullable
            )
        return
    op.alter_column("ai_market_shares", "item_id", existing_type=sa.Integer(), nullable=nullable)


def upgrade() -> None:
    # ai_market_shares：item_id 改为可空，新增「分享个人资产」所需列
    _alter_item_id_nullable(True)
    op.add_column(
        "ai_market_shares",
        sa.Column("asset_type", sa.String(length=16), nullable=True, comment="资产类型: tool/skill/mcp/plugin（分享个人资产时）"),
    )
    op.add_column(
        "ai_market_shares",
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="个人资产快照（分享个人资产时）"),
    )
    op.add_column(
        "ai_market_shares",
        sa.Column("asset_name", sa.String(length=128), nullable=True, comment="个人资产名（分享记录快照）"),
    )
    op.add_column(
        "ai_market_shares",
        sa.Column("asset_icon", sa.String(length=256), nullable=True, comment="个人资产图标（分享记录快照）"),
    )
    op.add_column(
        "ai_market_shares",
        sa.Column("source_id", sa.Integer(), nullable=True, comment="来源真实资产 id（仅记录）"),
    )


def downgrade() -> None:
    op.drop_column("ai_market_shares", "source_id")
    op.drop_column("ai_market_shares", "asset_icon")
    op.drop_column("ai_market_shares", "asset_name")
    op.drop_column("ai_market_shares", "payload")
    op.drop_column("ai_market_shares", "asset_type")
    _alter_item_id_nullable(False)
