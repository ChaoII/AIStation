"""新增人脸底库表 video_face_gallery（FACE_REC/STRANGER 的数据资产）

Revision ID: b3c1d2e3f4a5
Revises: e6f7a8b9c0d1
Create Date: 2026-09-17

设计（无 pgvector 依赖，PG / SQLite / MySQL 均可重放）：
- ``embedding`` 用 JSON 列存 float 数组（PG 为 JSONB，SQLite/MySQL 由
  ``dialect_compat`` 渲染为 JSON），相似度在应用层算余弦；
- ``dimension`` 冗余记录维度，比对时先按维度过滤（避免跨模型误比）；
- 同人员允许多行（多张底图），匹配取最大相似度。

性能上限与升级路径见 ``backend/app/api/v1/module_video/face_gallery/store.py``：
底库规模约数千条以内可接受；上量后升级为 pgvector 向量列 + ivfflat/hnsw 索引。
"""
from collections.abc import Sequence

from alembic import op

from app.alembic.dialect_compat import dialect_name, is_postgres

# revision identifiers, used by Alembic.
revision: str = "b3c1d2e3f4a5"
down_revision: str | Sequence[str] | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 与 FaceGalleryModel 元数据对齐（ModelMixin + UserMixin + 业务列）
_TABLE_DDL: str = """
CREATE TABLE IF NOT EXISTS video_face_gallery (
    id SERIAL NOT NULL,
    uuid VARCHAR(64) NOT NULL,
    status VARCHAR(10) NOT NULL,
    description TEXT,
    created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    is_deleted BOOLEAN NOT NULL,
    deleted_time TIMESTAMP WITHOUT TIME ZONE,
    created_id INTEGER,
    updated_id INTEGER,
    deleted_id INTEGER,
    name VARCHAR(128) NOT NULL,
    person_no VARCHAR(64),
    model_key VARCHAR(64) NOT NULL,
    embedding JSONB NOT NULL,
    dimension INTEGER NOT NULL,
    face_image_url VARCHAR(512),
    PRIMARY KEY (id),
    FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_video_face_gallery_uuid ON video_face_gallery (uuid);
CREATE INDEX IF NOT EXISTS ix_video_face_gallery_id ON video_face_gallery (id);
CREATE INDEX IF NOT EXISTS ix_video_face_gallery_status ON video_face_gallery (status);
CREATE INDEX IF NOT EXISTS ix_video_face_gallery_created_time ON video_face_gallery (created_time);
CREATE INDEX IF NOT EXISTS ix_video_face_gallery_updated_time ON video_face_gallery (updated_time);
CREATE INDEX IF NOT EXISTS ix_video_face_gallery_is_deleted ON video_face_gallery (is_deleted);
CREATE INDEX IF NOT EXISTS ix_video_face_gallery_deleted_time ON video_face_gallery (deleted_time);
CREATE INDEX IF NOT EXISTS ix_video_face_gallery_created_id ON video_face_gallery (created_id);
CREATE INDEX IF NOT EXISTS ix_video_face_gallery_updated_id ON video_face_gallery (updated_id);
CREATE INDEX IF NOT EXISTS ix_video_face_gallery_deleted_id ON video_face_gallery (deleted_id);
CREATE INDEX IF NOT EXISTS ix_video_face_gallery_name ON video_face_gallery (name);
CREATE INDEX IF NOT EXISTS ix_video_face_gallery_person_no ON video_face_gallery (person_no);
"""


def _render_type(sql: str, dialect: str) -> str:
    """按方言降级 DDL 中的 PG 专属类型（与 a3f3956bb77b 同口径）。"""
    sql = sql.replace("JSONB", "JSON")
    sql = sql.replace("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP")
    if dialect == "sqlite":
        sql = sql.replace("SERIAL", "INTEGER")
    return sql


def upgrade() -> None:
    """建表（幂等）：PG 原样执行，SQLite/MySQL 做类型降级。"""
    bind = op.get_bind()
    dialect = dialect_name(bind)
    for stmt in _TABLE_DDL.split(";"):
        part = stmt.strip()
        if not part:
            continue
        op.execute(part if is_postgres(bind) else _render_type(part, dialect))


def downgrade() -> None:
    """回滚：删除底库表（其索引随表一并删除）。"""
    op.execute("DROP TABLE IF EXISTS video_face_gallery;")
