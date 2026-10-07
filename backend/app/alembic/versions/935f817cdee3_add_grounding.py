"""ai_query_messages add grounding (only this column)

Revision ID: 935f817cdee3
Revises: c7d2e5f8a9b1
Create Date: 2026-10-07 09:29:15.700007

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '935f817cdee3'
down_revision: Union[str, None] = 'c7d2e5f8a9b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'ai_query_messages',
        sa.Column('grounding', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('ai_query_messages', 'grounding')
