"""标注图片增加缩略图列、版本复合索引，并移除死字段 bucket_name

Revision ID: f9e8d7c6b5a4
Revises: c1d2e3f4a5b6
Create Date: 2026-09-18

背景：标注数据生命周期与媒体管线治理。

- ``annotation_image.thumbnail_key``：缩略图对象 key（可为空，老数据回退原图）；
- ``ix_annotation_image_dataset_status``：加速按数据集 + 状态过滤图片；
- ``ix_annotation_record_task_image_version``：标注版本按 (task,image,version) 查询/清理；
- 删除 ``annotation_dataset.bucket_name``：死字段，真实 bucket 由
  ``RUSTFS_BUCKET_PREFIX + env`` 推导，模型/接口均无引用。
"""
from collections.abc import Sequence

from alembic import op

from app.alembic.dialect_compat import portable_add_column, portable_drop_column

# revision identifiers, used by Alembic.
revision: str = "f9e8d7c6b5a4"
down_revision: str | Sequence[str] | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """加缩略图列与两个索引，删除 bucket_name。"""
    portable_add_column(
        "annotation_image", "thumbnail_key", "VARCHAR(512) NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_annotation_image_dataset_status "
        "ON annotation_image (dataset_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_annotation_record_task_image_version "
        "ON annotation_record (task_id, image_id, version)"
    )
    portable_drop_column("annotation_dataset", "bucket_name")


def downgrade() -> None:
    """回滚：恢复 bucket_name，删除索引与缩略图列。"""
    portable_add_column(
        "annotation_dataset",
        "bucket_name",
        "VARCHAR(64) NOT NULL DEFAULT 'aistation-annotation-dev'",
    )
    op.execute("DROP INDEX IF EXISTS ix_annotation_record_task_image_version")
    op.execute("DROP INDEX IF EXISTS ix_annotation_image_dataset_status")
    portable_drop_column("annotation_image", "thumbnail_key")
