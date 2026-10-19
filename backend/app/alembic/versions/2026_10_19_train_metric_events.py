"""train_metric_events：训练结构化事件表（简单模式 bridge）

Revision ID: 3f9c2a71d5e8
Revises: f6b7c8d9e0a1
Create Date: 2026-10-19 12:00:00.000000

说明：手写迁移。autogenerate 会因本项目数据库存在大量未被模型覆盖的
历史/影子表产生无关 DROP，因此只保留本次特性所需变更（一条 CREATE TABLE
+ 唯一约束 + 索引）。``has_table`` 幂等守卫保证重跑安全。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3f9c2a71d5e8"
down_revision: str | None = "f6b7c8d9e0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 幂等守卫：表已存在（如应用 create_all 先行建表 / 重跑）时直接跳过
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("train_metric_events"):
        return

    op.create_table(
        "train_metric_events",
        sa.Column("task_id", sa.Integer(), nullable=False, comment="训练任务ID"),
        sa.Column("seq", sa.Integer(), nullable=False, comment="事件序号（任务内单调递增）"),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, comment="事件时间（UTC aware）"),
        sa.Column("type", sa.String(length=16), nullable=False, comment="事件类型: env/step/log/..."),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment="事件载荷"),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.ForeignKeyConstraint(["task_id"], ["train_tasks.id"], onupdate="CASCADE", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "seq", name="uq_tme_task_seq"),
        comment="训练结构化事件表",
    )
    op.create_index("idx_tme_task_type_ts", "train_metric_events",
                    ["task_id", "type", "ts"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_tme_task_type_ts", table_name="train_metric_events")
    op.drop_table("train_metric_events")
