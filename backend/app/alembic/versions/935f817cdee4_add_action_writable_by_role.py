"""ai_action add writable_by_role

Revision ID: 935f817cdee4
Revises: 935f817cdee3
Create Date: 2026-10-07 11:20:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '935f817cdee4'
down_revision: str | None = '935f817cdee3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 插件表（ai_*）由应用 create_all 建立，**不在 alembic 链里**；
    # 空库只跑 alembic 时该表不存在，加列会直接崩（实测）。
    insp = sa.inspect(op.get_bind())
    if 'ai_action' not in insp.get_table_names():
        return
    if any(c["name"] == 'writable_by_role' for c in insp.get_columns('ai_action')):
        return
    op.add_column('ai_action', sa.Column('writable_by_role', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if 'ai_action' not in insp.get_table_names():
        return
    op.drop_column('ai_action', 'writable_by_role')
