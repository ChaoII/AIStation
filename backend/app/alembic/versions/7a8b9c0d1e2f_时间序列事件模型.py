"""时间序列事件标注模型 + time_series_count/time_series_id

Revision ID: 7a8b9c0d1e2f
Revises: 6a7b8c9d0e1f
Create Date: 2026-09-23

支持时间序列事件标注，新增时间序列媒体模型 ``annotation_time_series``：

- ``AnnotationType.TIME_SERIES_EVENT``（PG 枚举 ``annotationtype`` 新增值 ``TIME_SERIES_EVENT``）；
- 新增时间序列媒体 ``annotation_time_series``（ModelMixin + UserMixin + 时间序列业务字段）；
- ``annotation_dataset`` 新增 ``time_series_count``（时间序列计数列）；
- ``annotation_record`` 新增 ``time_series_id``（与 image_id/video_id/document_id/audio_id 五者互斥）。

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
revision: str = "7a8b9c0d1e2f"
down_revision: str | Sequence[str] | None = "6a7b8c9d0e1f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 与 AnnotationTimeSeriesModel 元数据对齐（ModelMixin + UserMixin + 时间序列业务字段）
# 注意：status 由继承的 ImageStatus 枚举覆盖，故本表仅有一个 status 列，
# 类型为 PG 的 imagestatus 枚举（见 a3f3956bb77b 建库定义）。
_TABLE_DDL: str = """
CREATE TABLE IF NOT EXISTS annotation_time_series (
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
    time_column VARCHAR(64) NOT NULL,
    value_columns JSONB NOT NULL,
    row_count INTEGER NOT NULL,
    time_unit VARCHAR(8) NOT NULL,
    start_time FLOAT,
    end_time FLOAT,
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
CREATE INDEX IF NOT EXISTS ix_annotation_timeseries_id ON annotation_time_series (id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_annotation_timeseries_uuid ON annotation_time_series (uuid);
CREATE INDEX IF NOT EXISTS ix_annotation_timeseries_created_time ON annotation_time_series (created_time);
CREATE INDEX IF NOT EXISTS ix_annotation_timeseries_updated_time ON annotation_time_series (updated_time);
CREATE INDEX IF NOT EXISTS ix_annotation_timeseries_is_deleted ON annotation_time_series (is_deleted);
CREATE INDEX IF NOT EXISTS ix_annotation_timeseries_deleted_time ON annotation_time_series (deleted_time);
CREATE INDEX IF NOT EXISTS ix_annotation_timeseries_created_id ON annotation_time_series (created_id);
CREATE INDEX IF NOT EXISTS ix_annotation_timeseries_updated_id ON annotation_time_series (updated_id);
CREATE INDEX IF NOT EXISTS ix_annotation_timeseries_deleted_id ON annotation_time_series (deleted_id);
CREATE INDEX IF NOT EXISTS ix_annotation_timeseries_dataset_status ON annotation_time_series (dataset_id, status);
"""


def _render_type(sql: str, dialect: str) -> str:
    """跨方言降级 DDL 中的 PG 专属类型（与 766b3e7a1545 同策略）。"""
    sql = sql.replace("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP")
    sql = sql.replace("JSONB", "JSON")
    if dialect == "sqlite":
        sql = sql.replace("SERIAL", "INTEGER")
    return sql


def upgrade() -> None:
    """新增 TIME_SERIES_EVENT 枚举值 + time_series_count 列 + annotation_time_series 表 + time_series_id 列。"""
    bind = op.get_bind()
    # 1) PostgreSQL 枚举新增 TIME_SERIES_EVENT；SQLite/MySQL 该列为 VARCHAR/CHECK（无需新增枚举）。
    if is_postgres(bind):
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE annotationtype ADD VALUE IF NOT EXISTS 'TIME_SERIES_EVENT'"
            )
    # 2) annotation_dataset 新增时间序列计数列（带默认值，兼容既有数据集）。
    portable_add_column("annotation_dataset", "time_series_count", "INTEGER NOT NULL DEFAULT 0")
    # 3) 新建时间序列媒体表（跨方言降级渲染）。
    dialect = dialect_name(bind)
    for stmt in _TABLE_DDL.split(";"):
        part = stmt.strip()
        if not part:
            continue
        op.execute(part if is_postgres(bind) else _render_type(part, dialect))
    # 4) annotation_record 新增 time_series_id 列；PG 上补外键。
    portable_add_column("annotation_record", "time_series_id", "INTEGER")
    op.create_index(
        "ix_annotation_record_task_timeseries_version",
        "annotation_record",
        ["task_id", "time_series_id", "version"],
    )
    if is_postgres(bind):
        op.execute(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = "
            "'fk_annotation_record_time_series_id') THEN "
            "ALTER TABLE annotation_record ADD CONSTRAINT fk_annotation_record_time_series_id "
            "FOREIGN KEY (time_series_id) REFERENCES annotation_time_series (id); "
            "END IF; END $$;"
        )


def downgrade() -> None:
    """回滚：删除 time_series_id/time_series_count 列与 annotation_time_series 表（枚举值 PG 不支持移除）。"""
    bind = op.get_bind()
    # 先删依赖 annotation_time_series 的外键（仅 PG），再删表，避免 DependentObjectsStillExist。
    if is_postgres(bind):
        op.execute("ALTER TABLE annotation_record DROP CONSTRAINT IF EXISTS fk_annotation_record_time_series_id")
    # 先删索引再删列：PG 在 DROP COLUMN 时会级联删除依赖该列的索引，
    # 若反过来会因索引已不存在而报错。
    op.drop_index(
        "ix_annotation_record_task_timeseries_version",
        table_name="annotation_record",
    )
    portable_drop_column("annotation_record", "time_series_id")
    portable_drop_column("annotation_dataset", "time_series_count")
    op.execute("DROP INDEX IF EXISTS ix_annotation_timeseries_dataset_status")
    op.execute("DROP TABLE IF EXISTS annotation_time_series")
