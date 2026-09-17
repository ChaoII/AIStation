"""底库表新增 kind 判别列（人脸 / 跨镜重识别复用同一张表）

Revision ID: c1d2e3f4a5b6
Revises: b3c1d2e3f4a5
Create Date: 2026-09-18

背景（B4）：``reid_match``（跨镜重识别）与 face_match/stranger（人脸）共用
``objects[].embedding`` 字段，云端靠底库 ``kind`` 而非字段区分用途：

- ``kind='face'``：人脸底库（FACE_REC/STRANGER）；
- ``kind='reid'``：跨镜底库（REID_TRACK）。

复用既有 ``video_face_gallery`` 表（不新建第二张表），仅新增一列 + 索引：
- 老数据 ``kind`` 回填为 ``'face'``（默认值），人脸行为逐字节不变；
- 方言可移植：PG 用 ``ADD COLUMN IF NOT EXISTS``，SQLite/MySQL 经
  ``portable_add_column`` 先探测后添加；索引在两种方言下均支持 ``IF NOT EXISTS``。
"""
from collections.abc import Sequence

from alembic import op

from app.alembic.dialect_compat import portable_add_column

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "b3c1d2e3f4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """新增 ``kind`` 列（NOT NULL DEFAULT 'face'）与索引（幂等、方言可移植）。"""
    portable_add_column(
        "video_face_gallery", "kind", "VARCHAR(16) NOT NULL DEFAULT 'face'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_video_face_gallery_kind "
        "ON video_face_gallery (kind)"
    )


def downgrade() -> None:
    """回滚：删除索引与 ``kind`` 列。"""
    op.execute("DROP INDEX IF EXISTS ix_video_face_gallery_kind")
    op.execute("ALTER TABLE video_face_gallery DROP COLUMN IF EXISTS kind")
