"""算法模型新增上一版本字段（模型热更新回滚用）

Revision ID: b2c3d4e5f6a7
Revises: 183fb76b1184
Create Date: 2026-09-15
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "183fb76b1184"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 仅新增两列（可空），既有数据不受影响
    op.add_column(
        "video_algorithms",
        sa.Column("previous_model_path", sa.String(512), nullable=True, comment="上一版本模型路径（回滚用）"),
    )
    op.add_column(
        "video_algorithms",
        sa.Column("previous_version", sa.String(32), nullable=True, comment="上一版本号（回滚用）"),
    )


def downgrade() -> None:
    op.drop_column("video_algorithms", "previous_version")
    op.drop_column("video_algorithms", "previous_model_path")
