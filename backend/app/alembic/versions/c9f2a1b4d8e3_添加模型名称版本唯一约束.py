"""添加 train_models name+version 唯一约束（软删除记录不参与）

Revision ID: c9f2a1b4d8e3
Revises: b744384adf6f
Create Date: 2026-07-15 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9f2a1b4d8e3"
down_revision: str | None = "b744384adf6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX uq_train_models_name_version
        ON train_models (name, version)
        WHERE is_deleted = 0
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_train_models_name_version")
