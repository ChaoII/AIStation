"""annotation_image 增加 content_hash（内容哈希去重）

Revision ID: a7b8c9d0e1f2
Revises: f9e8d7c6b5a4
Create Date: 2026-09-18

- 新增 ``content_hash``：图片内容 sha256，用于上传/导入按内容去重；
- 新增索引 ``(dataset_id, content_hash)`` 加速查重。
"""
from collections.abc import Sequence

from alembic import op

from app.alembic.dialect_compat import portable_add_column

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f9e8d7c6b5a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """新增 content_hash 列与 (dataset_id, content_hash) 索引。"""
    portable_add_column("annotation_image", "content_hash", "VARCHAR(64) NULL")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_annotation_image_dataset_hash "
        "ON annotation_image (dataset_id, content_hash)"
    )


def downgrade() -> None:
    """回滚：删除索引与列。"""
    op.execute("DROP INDEX IF EXISTS ix_annotation_image_dataset_hash")
    from app.alembic.dialect_compat import portable_drop_column

    portable_drop_column("annotation_image", "content_hash")
