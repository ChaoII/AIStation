"""ai_query_messages add grounding (only this column)

Revision ID: 935f817cdee3
Revises: c7d2e5f8a9b1
Create Date: 2026-10-07 09:29:15.700007

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '935f817cdee3'
down_revision: str | None = 'c7d2e5f8a9b1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 插件表（ai_query_*）由应用 create_all 建立，**不在 alembic 链里**；
    # 空库只跑 alembic 时该表不存在，加列会直接崩（实测）。
    insp = sa.inspect(op.get_bind())
    if 'ai_query_messages' not in insp.get_table_names():
        return
    if any(c["name"] == 'grounding' for c in insp.get_columns('ai_query_messages')):
        return
    op.add_column(
        'ai_query_messages',
        sa.Column('grounding', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if 'ai_query_messages' not in insp.get_table_names():
        return
    op.drop_column('ai_query_messages', 'grounding')
