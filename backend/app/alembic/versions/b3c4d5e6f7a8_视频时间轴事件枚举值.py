"""视频时间轴事件枚举值

Revision ID: b3c4d5e6f7a8
Revises: 7a8b9c0d1e2f
Create Date: 2026-09-23

支持视频时间轴事件标注（video_event），向 PG 枚举 ``annotationtype`` 新增值 ``VIDEO_EVENT``。

video_event 复用既有的视频媒体模型 ``annotation_video``（在 766b3e7a1545 建立）与
``annotation_record.video_id`` 锚定列，仅缺该枚举值即可创建任务。SQLite/MySQL 该列为
VARCHAR/CHECK，无需新增枚举。
"""
from collections.abc import Sequence

from alembic import op

from app.alembic.dialect_compat import is_postgres

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: str | Sequence[str] | None = "7a8b9c0d1e2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """PostgreSQL 枚举新增 VIDEO_EVENT；SQLite/MySQL 该列为 VARCHAR/CHECK（无需新增枚举）。"""
    bind = op.get_bind()
    if is_postgres(bind):
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE annotationtype ADD VALUE IF NOT EXISTS 'VIDEO_EVENT'")


def downgrade() -> None:
    """回滚：PG 枚举不支持移除值，故为空操作（与 AUDIO_EVENT/TIME_SERIES_EVENT 迁移一致）。"""
    pass
