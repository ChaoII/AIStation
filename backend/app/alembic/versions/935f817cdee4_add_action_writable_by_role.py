"""ai_action add writable_by_role

Revision ID: 935f817cdee4
Revises: 935f817cdee3
Create Date: 2026-10-07 11:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '935f817cdee4'
down_revision: Union[str, None] = '935f817cdee3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ai_action', sa.Column('writable_by_role', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('ai_action', 'writable_by_role')
