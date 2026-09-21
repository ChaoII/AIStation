"""semantic_segmentation enum

Revision ID: bfda605e491e
Revises: a7b8c9d0e1f2
"""
from collections.abc import Sequence

from alembic import op

from app.alembic.dialect_compat import is_postgres

revision: str = "bfda605e491e"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """给 annotationtype 枚举增加 SEMANTIC_SEGMENTATION 值（仅 PostgreSQL）。

    SQLAlchemy 以枚举成员 NAME（大写）存储，而非 .value（小写），
    因此必须添加大写值 'SEMANTIC_SEGMENTATION'。
    """
    if is_postgres(op.get_bind()):
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE annotationtype ADD VALUE IF NOT EXISTS "
                "'SEMANTIC_SEGMENTATION'"
            )


def downgrade() -> None:
    """PG 不支持移除枚举值，downgrade 为空操作（保留该值）。"""
    pass
