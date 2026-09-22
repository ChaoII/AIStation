"""文本 NER 文档模型 + document_count/document_id

Revision ID: 5a6b7c8d9e0f
Revises: b5e6f7a8c9d0
Create Date: 2026-09-22

支持文本 NER 标注，新增文档媒体模型 ``annotation_document``：

- ``AnnotationType.TEXT_NER``（PG 枚举 ``annotationtype`` 新增值 ``TEXT_NER``）；
- 新增文本媒体 ``annotation_document``（ModelMixin + UserMixin + 业务字段）；
- ``annotation_dataset`` 新增 ``document_count``（文档计数列）；
- ``annotation_record`` 新增 ``document_id``（与 image_id/video_id 三者互斥）。

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
revision: str = "5a6b7c8d9e0f"
down_revision: str | Sequence[str] | None = "b5e6f7a8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 与 AnnotationDocumentModel 元数据对齐（ModelMixin + UserMixin + 业务字段）
# 注意：status 由继承的 ImageStatus 枚举覆盖，故本表仅有一个 status 列，
# 类型为 PG 的 imagestatus 枚举（见 a3f3956bb77b 建库定义）。
_TABLE_DDL: str = """
CREATE TABLE IF NOT EXISTS annotation_document (
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
    filename VARCHAR(255) NOT NULL,
    object_key VARCHAR(512) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    encoding VARCHAR(32) NOT NULL,
    character_count INTEGER NOT NULL,
    line_count INTEGER NOT NULL,
    locked_by INTEGER,
    locked_at TIMESTAMP WITHOUT TIME ZONE,
    annotation_count INTEGER NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY(dataset_id) REFERENCES annotation_dataset (id)
);
CREATE INDEX IF NOT EXISTS ix_annotation_document_id ON annotation_document (id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_annotation_document_uuid ON annotation_document (uuid);
CREATE INDEX IF NOT EXISTS ix_annotation_document_created_time ON annotation_document (created_time);
CREATE INDEX IF NOT EXISTS ix_annotation_document_updated_time ON annotation_document (updated_time);
CREATE INDEX IF NOT EXISTS ix_annotation_document_is_deleted ON annotation_document (is_deleted);
CREATE INDEX IF NOT EXISTS ix_annotation_document_deleted_time ON annotation_document (deleted_time);
CREATE INDEX IF NOT EXISTS ix_annotation_document_created_id ON annotation_document (created_id);
CREATE INDEX IF NOT EXISTS ix_annotation_document_updated_id ON annotation_document (updated_id);
CREATE INDEX IF NOT EXISTS ix_annotation_document_deleted_id ON annotation_document (deleted_id);
CREATE INDEX IF NOT EXISTS ix_annotation_document_dataset_status ON annotation_document (dataset_id, status);
CREATE INDEX IF NOT EXISTS ix_annotation_document_dataset_hash ON annotation_document (dataset_id, content_hash);
"""


def _render_type(sql: str, dialect: str) -> str:
    """跨方言降级 DDL 中的 PG 专属类型（与 766b3e7a1545 同策略）。"""
    sql = sql.replace("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP")
    if dialect == "sqlite":
        sql = sql.replace("SERIAL", "INTEGER")
    return sql


def upgrade() -> None:
    """新增 TEXT_NER 枚举值 + document_count 列 + annotation_document 表 + document_id 列。"""
    bind = op.get_bind()
    # 1) PostgreSQL 枚举新增 TEXT_NER；SQLite/MySQL 该列为 VARCHAR/CHECK（无需新增枚举）。
    if is_postgres(bind):
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE annotationtype ADD VALUE IF NOT EXISTS 'TEXT_NER'"
            )
    # 2) annotation_dataset 新增文档计数列（带默认值，兼容既有数据集）。
    portable_add_column("annotation_dataset", "document_count", "INTEGER NOT NULL DEFAULT 0")
    # 3) 新建文本媒体表（跨方言降级渲染）。
    dialect = dialect_name(bind)
    for stmt in _TABLE_DDL.split(";"):
        part = stmt.strip()
        if not part:
            continue
        op.execute(part if is_postgres(bind) else _render_type(part, dialect))
    # 4) annotation_record 新增 document_id 列；PG 上补外键。
    portable_add_column("annotation_record", "document_id", "INTEGER")
    op.create_index(
        "ix_annotation_record_task_document_version",
        "annotation_record",
        ["task_id", "document_id", "version"],
    )
    if is_postgres(bind):
        op.execute(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = "
            "'fk_annotation_record_document_id') THEN "
            "ALTER TABLE annotation_record ADD CONSTRAINT fk_annotation_record_document_id "
            "FOREIGN KEY (document_id) REFERENCES annotation_document (id); "
            "END IF; END $$;"
        )


def downgrade() -> None:
    """回滚：删除 document_id/document_count 列与 annotation_document 表（枚举值 PG 不支持移除）。"""
    # 先删依赖 annotation_document 的外键，再删表，避免 DependentObjectsStillExist。
    op.execute("ALTER TABLE annotation_record DROP CONSTRAINT IF EXISTS fk_annotation_record_document_id")
    # 先删索引再删列：PG 在 DROP COLUMN 时会级联删除依赖该列的索引，
    # 若反过来会因索引已不存在而报错。
    op.drop_index(
        "ix_annotation_record_task_document_version",
        table_name="annotation_record",
    )
    portable_drop_column("annotation_record", "document_id")
    portable_drop_column("annotation_dataset", "document_count")
    op.execute("DROP INDEX IF EXISTS ix_annotation_document_dataset_hash")
    op.execute("DROP INDEX IF EXISTS ix_annotation_document_dataset_status")
    op.execute("DROP TABLE IF EXISTS annotation_document")
