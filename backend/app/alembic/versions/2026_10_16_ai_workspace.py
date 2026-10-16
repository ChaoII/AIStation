"""AI 工作台：统一分类表 + 定时任务表 + 工作流/应用分类列

Revision ID: a1b2c3d4e5f6
Revises: d3f4a5b6c789
Create Date: 2026-10-16 12:00:00.000000

说明：手写迁移。autogenerate 会因本项目存在大量未被模型覆盖的历史/影子表
（ont_* 等）产生无关 DROP，因此只保留本特性所需变更。
插件表（ai_agents/ai_workflows/ai_apps 等）不由迁移链创建，增列/建表前
用 ``sa.inspect(bind).has_table()`` 判断，避免空库全链重放（SQLite 回归）失败。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "beef01cafe02"
down_revision: str | None = "d3f4a5b6c789"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "ai_workspace_categories" not in insp.get_table_names():
        op.create_table(
            "ai_workspace_categories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=64), nullable=False, comment="分类名称"),
            sa.Column("parent_id", sa.Integer(), nullable=True, comment="父分类ID（空为顶级）"),
            sa.Column("icon", sa.String(length=64), nullable=True, comment="图标"),
            sa.Column("color", sa.String(length=32), nullable=True, comment="主题色"),
            sa.Column("sort", sa.Integer(), nullable=True, comment="排序"),
            sa.Column(
                "status", sa.String(length=16), nullable=True, default="1", comment="状态"
            ),
            sa.Column("created_time", sa.DateTime(), nullable=True),
            sa.Column("updated_time", sa.DateTime(), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), nullable=True, default=False),
            sa.Column("deleted_time", sa.DateTime(), nullable=True),
            sa.Column("created_id", sa.Integer(), nullable=True),
            sa.Column("updated_id", sa.Integer(), nullable=True),
            sa.Column("deleted_id", sa.Integer(), nullable=True),
            sa.Column("uuid", sa.String(length=36), nullable=True),
        )

    if "ai_workspace_cron" not in insp.get_table_names():
        op.create_table(
            "ai_workspace_cron",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=128), nullable=False, comment="任务名称"),
            sa.Column("description", sa.String(length=512), nullable=True, comment="任务描述"),
            sa.Column("cron", sa.String(length=128), nullable=True, comment="cron 表达式"),
            sa.Column(
                "target_type", sa.String(length=32), nullable=True, default="agent",
                comment="执行目标类型 agent/workflow/app",
            ),
            sa.Column("target_id", sa.Integer(), nullable=True, comment="执行目标 ID"),
            sa.Column("category_id", sa.Integer(), nullable=True, comment="所属分类ID"),
            sa.Column("enabled", sa.Boolean(), nullable=True, default=False, comment="是否启用"),
            sa.Column("last_run_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_run_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=True, default="1", comment="状态"),
            sa.Column("created_time", sa.DateTime(), nullable=True),
            sa.Column("updated_time", sa.DateTime(), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), nullable=True, default=False),
            sa.Column("deleted_time", sa.DateTime(), nullable=True),
            sa.Column("created_id", sa.Integer(), nullable=True),
            sa.Column("updated_id", sa.Integer(), nullable=True),
            sa.Column("deleted_id", sa.Integer(), nullable=True),
            sa.Column("uuid", sa.String(length=36), nullable=True),
        )

    # 给已存在的工作流/应用表加分类列（插件表，可能不在迁移链；用 has_table 守卫）
    for tbl in ("ai_workflows", "ai_apps"):
        if tbl not in insp.get_table_names():
            continue
        cols = {c["name"] for c in insp.get_columns(tbl)}
        if "category_id" not in cols:
            op.add_column(
                tbl,
                sa.Column("category_id", sa.Integer(), nullable=True, comment="工作台分类ID"),
            )


def downgrade() -> None:
    # 工作流/应用分类列
    for tbl in ("ai_workflows", "ai_apps"):
        op.drop_column(tbl, "category_id")
    # 分类/定时任务表
    op.drop_table("ai_workspace_cron")
    op.drop_table("ai_workspace_categories")
