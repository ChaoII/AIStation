"""annotation_record 增加 video_id / frame_index，image_id 改为可空

Revision ID: b5e6f7a8c9d0
Revises: 766b3e7a1545
Create Date: 2026-09-22

支持帧级视频标注：``annotation_record`` 表新增视频注解字段。

- 新增 ``video_id``（外键 → ``annotation_video.id``，可空）。
- 新增 ``frame_index``（整型，可空），视频标注非空。
- ``image_id`` 改为可空（图片标注与视频标注二选一）。
- 新增复合索引 ``ix_annotation_record_task_video_frame_version``。

说明：本迁移为手工改写的最小幂等脚本（沿用本任务分支 Task 1 的惯例，
避免 autogenerate 在 dev 库上引入大量与任务无关的漂移变更）。
"""
from collections.abc import Sequence

from alembic import op

from app.alembic.dialect_compat import (
    is_postgres,
    portable_add_column,
    portable_drop_column,
)

# revision identifiers, used by Alembic.
revision: str = "b5e6f7a8c9d0"
down_revision: str | Sequence[str] | None = "766b3e7a1545"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """新增视频标注字段并为 image_id 解除 NOT NULL。"""
    bind = op.get_bind()
    portable_add_column("annotation_record", "video_id", "INTEGER")
    portable_add_column("annotation_record", "frame_index", "INTEGER")
    if is_postgres(bind):
        # 让 image_id 允许为空（图片标注与视频标注二选一）
        op.execute("ALTER TABLE annotation_record ALTER COLUMN image_id DROP NOT NULL")
        # 新增 video_id 外键（仅在 PG 上以幂等方式添加；SQLite/MySQL 测试库不依赖 FK）
        op.execute(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = "
            "'fk_annotation_record_video_id') THEN "
            "ALTER TABLE annotation_record ADD CONSTRAINT fk_annotation_record_video_id "
            "FOREIGN KEY (video_id) REFERENCES annotation_video (id); "
            "END IF; END $$;"
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_annotation_record_task_video_frame_version "
        "ON annotation_record (task_id, video_id, frame_index, version)"
    )


def downgrade() -> None:
    """回滚：删除视频标注索引/外键与字段，恢复 image_id NOT NULL。"""
    op.execute("DROP INDEX IF EXISTS ix_annotation_record_task_video_frame_version")
    op.execute("ALTER TABLE annotation_record DROP CONSTRAINT IF EXISTS fk_annotation_record_video_id")
    portable_drop_column("annotation_record", "frame_index")
    portable_drop_column("annotation_record", "video_id")
    bind = op.get_bind()
    if is_postgres(bind):
        op.execute(
            "UPDATE annotation_record SET image_id = COALESCE(image_id, 0) "
            "WHERE image_id IS NULL"
        )
        op.execute("ALTER TABLE annotation_record ALTER COLUMN image_id SET NOT NULL")
