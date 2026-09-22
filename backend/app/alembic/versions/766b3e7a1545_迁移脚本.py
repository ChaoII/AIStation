"""video_detection 枚举 + annotation_video 表 + annotation_dataset.video_count

Revision ID: 766b3e7a1545
Revises: 9a8b7c6d5e4f
Create Date: 2026-09-22

背景：帧级视频检测标注需要新增视频媒体表。

- ``AnnotationType.VideoDetection`` → PG 枚举 ``annotationtype`` 增加值
  ``VIDEO_DETECTION``（SQLAlchemy 以枚举成员 NAME（大写）存储）；
- 新增视频媒体表 ``annotation_video``（ModelMixin + UserMixin + 业务列）；
- ``annotation_dataset`` 增加 ``video_count``（视频总数）字段。

说明：本迁移由自动生成脚本产生的差异多为无关噪声（dev 库与模型历史漂移），
已手工收敛为「仅与本任务相关」的幂等操作。enum 的添加仅 PostgreSQL 需要
（SQLite/MySQL 将 ENUM 渲染为 VARCHAR/CHECK）。
"""
from collections.abc import Sequence

from alembic import op

from app.alembic.dialect_compat import (
    dialect_name,
    is_postgres,
    portable_add_column,
    portable_drop_column,
)

# revision identifiers, used by Alembic.
revision: str = "766b3e7a1545"
down_revision: str | Sequence[str] | None = "9a8b7c6d5e4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 与 AnnotationVideoModel 元数据对齐（ModelMixin + UserMixin + 业务列）。
# 注意：status 列继承自 ImageStatus 枚举（覆盖 ModelMixin 的 status 字符串列），
# 故表内只有这一个 status 列，类型为 PG 的 imagestatus 枚举（由 a3f3956bb77b 创建）。
_TABLE_DDL: str = """
CREATE TABLE IF NOT EXISTS annotation_video (
    id SERIAL NOT NULL,
    uuid VARCHAR(64) NOT NULL,
    status imagestatus NOT NULL,
    description TEXT,
    created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    is_deleted BOOLEAN NOT NULL,
    deleted_time TIMESTAMP WITHOUT TIME ZONE,
    created_id INTEGER,
    updated_id INTEGER,
    deleted_id INTEGER,
    dataset_id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    object_key VARCHAR(512) NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    duration FLOAT NOT NULL,
    fps FLOAT NOT NULL,
    frame_count INTEGER NOT NULL,
    thumbnail_key VARCHAR(512),
    locked_by INTEGER,
    locked_at TIMESTAMP WITHOUT TIME ZONE,
    annotation_count INTEGER NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY(dataset_id) REFERENCES annotation_dataset (id)
);
CREATE INDEX IF NOT EXISTS ix_annotation_video_id ON annotation_video (id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_annotation_video_uuid ON annotation_video (uuid);
CREATE INDEX IF NOT EXISTS ix_annotation_video_created_time ON annotation_video (created_time);
CREATE INDEX IF NOT EXISTS ix_annotation_video_updated_time ON annotation_video (updated_time);
CREATE INDEX IF NOT EXISTS ix_annotation_video_is_deleted ON annotation_video (is_deleted);
CREATE INDEX IF NOT EXISTS ix_annotation_video_deleted_time ON annotation_video (deleted_time);
CREATE INDEX IF NOT EXISTS ix_annotation_video_created_id ON annotation_video (created_id);
CREATE INDEX IF NOT EXISTS ix_annotation_video_updated_id ON annotation_video (updated_id);
CREATE INDEX IF NOT EXISTS ix_annotation_video_deleted_id ON annotation_video (deleted_id);
CREATE INDEX IF NOT EXISTS ix_annotation_video_dataset_status ON annotation_video (dataset_id, status);
"""


def _render_type(sql: str, dialect: str) -> str:
    """按方言降级 DDL 中的 PG 专属类型（与 a3f3956bb77b 同口径）。"""
    sql = sql.replace("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP")
    if dialect == "sqlite":
        sql = sql.replace("SERIAL", "INTEGER")
    return sql


def upgrade() -> None:
    """加 VIDEO_DETECTION 枚举值 + video_count 列 + annotation_video 建表（幂等）。"""
    bind = op.get_bind()
    # 1) PostgreSQL 枚举增加 VIDEO_DETECTION（SQLite/MySQL 走 VARCHAR/CHECK，无需）
    if is_postgres(bind):
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE annotationtype ADD VALUE IF NOT EXISTS 'VIDEO_DETECTION'"
            )
    # 2) annotation_dataset 增加视频总数（带默认值，兼容已有数据集行）
    portable_add_column("annotation_dataset", "video_count", "INTEGER NOT NULL DEFAULT 0")
    # 3) 建表（幂等），按方言降级类型
    dialect = dialect_name(bind)
    for stmt in _TABLE_DDL.split(";"):
        part = stmt.strip()
        if not part:
            continue
        op.execute(part if is_postgres(bind) else _render_type(part, dialect))


def downgrade() -> None:
    """回滚：删除索引、表与 video_count 列；enum 值 PG 不支持移除，保留。"""
    op.execute("DROP INDEX IF EXISTS ix_annotation_video_dataset_status")
    op.execute("DROP TABLE IF EXISTS annotation_video")
    portable_drop_column("annotation_dataset", "video_count")
