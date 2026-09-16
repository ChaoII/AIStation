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


def _has_column(table: str, column: str) -> bool:
    """列存在探测：兼容「先重启兜底补列、后跑迁移」的顺序（避免 DuplicateColumn）。"""
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return column in {col["name"] for col in insp.get_columns(table)}


def upgrade() -> None:
    # 仅新增两列（可空），既有数据不受影响；列已存在（兜底补列）则跳过
    if not _has_column("video_algorithms", "previous_model_path"):
        op.add_column(
            "video_algorithms",
            sa.Column("previous_model_path", sa.String(512), nullable=True, comment="上一版本模型路径（回滚用）"),
        )
    if not _has_column("video_algorithms", "previous_version"):
        op.add_column(
            "video_algorithms",
            sa.Column("previous_version", sa.String(32), nullable=True, comment="上一版本号（回滚用）"),
        )


def downgrade() -> None:
    op.drop_column("video_algorithms", "previous_version")
    op.drop_column("video_algorithms", "previous_model_path")
