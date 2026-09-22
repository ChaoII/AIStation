"""音频事件标注音频模型 + audio_count/audio_id

Revision ID: 6a7b8c9d0e1f
Revises: 5a6b7c8d9e0f
Create Date: 2026-09-23

支持音频事件(SED)标注，新增音频媒体模型 ``annotation_audio``：

- ``AnnotationType.AUDIO_EVENT``（PG 枚举 ``annotationtype`` 新增值 ``AUDIO_EVENT``）；
- 新增音频媒体 ``annotation_audio``（ModelMixin + UserMixin + 音频业务字段）；
- ``annotation_dataset`` 新增 ``audio_count``（音频计数列）；
- ``annotation_record`` 新增 ``audio_id``（与 image_id/video_id/document_id 四者互斥）。

说明：迁移为手工编写，仅包含与本功能相关的变更，并未引入 dev 库
与模型的历史漂移（因 autogenerate 会产生大量无关变更）。处理跨方言：
表格用 ``CREATE TABLE IF NOT EXISTS``，补列走 ``portable_add_column``，
枚举值新增仅 PostgreSQL 支持，SQLite/MySQL 以 VARCHAR/CHECK 降级。
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
revision: str = "6a7b8c9d0e1f"
down_revision: str | Sequence[str] | None = "5a6b7c8d9e0f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 与 AnnotationAudioModel 元数据对齐（ModelMixin + UserMixin + 音频业务字段）
# 注意：status 由继承的 ImageStatus 枚举覆盖，故本表仅有一个 status 列，
# 类型为 PG 的 imagestatus 枚举（见 a3f3956bb77b 建库定义）。
_TABLE_DDL: str = """
CREATE TABLE IF NOT EXISTS annotation_audio (
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
    duration FLOAT NOT NULL,
    sample_rate INTEGER NOT NULL,
    channels INTEGER NOT NULL,
    bitrate INTEGER,
    size_bytes INTEGER NOT NULL,
    locked_by INTEGER,
    locked_at TIMESTAMP WITHOUT TIME ZONE,
    annotation_count INTEGER NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY(dataset_id) REFERENCES annotation_dataset (id)
);
CREATE INDEX IF NOT EXISTS ix_annotation_audio_id ON annotation_audio (id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_annotation_audio_uuid ON annotation_audio (uuid);
CREATE INDEX IF NOT EXISTS ix_annotation_audio_created_time ON annotation_audio (created_time);
CREATE INDEX IF NOT EXISTS ix_annotation_audio_updated_time ON annotation_audio (updated_time);
CREATE INDEX IF NOT EXISTS ix_annotation_audio_is_deleted ON annotation_audio (is_deleted);
CREATE INDEX IF NOT EXISTS ix_annotation_audio_deleted_time ON annotation_audio (deleted_time);
CREATE INDEX IF NOT EXISTS ix_annotation_audio_created_id ON annotation_audio (created_id);
CREATE INDEX IF NOT EXISTS ix_annotation_audio_updated_id ON annotation_audio (updated_id);
CREATE INDEX IF NOT EXISTS ix_annotation_audio_deleted_id ON annotation_audio (deleted_id);
CREATE INDEX IF NOT EXISTS ix_annotation_audio_dataset_status ON annotation_audio (dataset_id, status);
"""


def _render_type(sql: str, dialect: str) -> str:
    """跨方言降级 DDL 中的 PG 专属类型（与 766b3e7a1545 同策略）。"""
    sql = sql.replace("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP")
    if dialect == "sqlite":
        sql = sql.replace("SERIAL", "INTEGER")
    return sql


def upgrade() -> None:
    """新增 AUDIO_EVENT 枚举值 + audio_count 列 + annotation_audio 表 + audio_id 列。"""
    bind = op.get_bind()
    # 1) PostgreSQL 枚举新增 AUDIO_EVENT；SQLite/MySQL 该列为 VARCHAR/CHECK（无需新增枚举）。
    if is_postgres(bind):
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE annotationtype ADD VALUE IF NOT EXISTS 'AUDIO_EVENT'"
            )
    # 2) annotation_dataset 新增音频计数列（带默认值，兼容既有数据集）。
    portable_add_column("annotation_dataset", "audio_count", "INTEGER NOT NULL DEFAULT 0")
    # 3) 新建音频媒体表（跨方言降级渲染）。
    dialect = dialect_name(bind)
    for stmt in _TABLE_DDL.split(";"):
        part = stmt.strip()
        if not part:
            continue
        op.execute(part if is_postgres(bind) else _render_type(part, dialect))
    # 4) annotation_record 新增 audio_id 列；PG 上补外键。
    portable_add_column("annotation_record", "audio_id", "INTEGER")
    op.create_index(
        "ix_annotation_record_task_audio_version",
        "annotation_record",
        ["task_id", "audio_id", "version"],
    )
    if is_postgres(bind):
        op.execute(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = "
            "'fk_annotation_record_audio_id') THEN "
            "ALTER TABLE annotation_record ADD CONSTRAINT fk_annotation_record_audio_id "
            "FOREIGN KEY (audio_id) REFERENCES annotation_audio (id); "
            "END IF; END $$;"
        )


def downgrade() -> None:
    """回滚：删除 audio_id/audio_count 列与 annotation_audio 表（枚举值 PG 不支持移除）。"""
    # 先删依赖 annotation_audio 的外键，再删表，避免 DependentObjectsStillExist。
    op.execute("ALTER TABLE annotation_record DROP CONSTRAINT IF EXISTS fk_annotation_record_audio_id")
    # 先删索引再删列：PG 在 DROP COLUMN 时会级联删除依赖该列的索引，
    # 若反过来会因索引已不存在而报错。
    op.drop_index(
        "ix_annotation_record_task_audio_version",
        table_name="annotation_record",
    )
    portable_drop_column("annotation_record", "audio_id")
    portable_drop_column("annotation_dataset", "audio_count")
    op.execute("DROP INDEX IF EXISTS ix_annotation_audio_dataset_status")
    op.execute("DROP TABLE IF EXISTS annotation_audio")
