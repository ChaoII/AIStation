"""定时任务补「上次执行结果」四列

卡片上要直接看到上次跑成没跑成、跑了多久、结果是什么，
不用再去调用日志里翻。四列都可空，存量行不受影响。

Revision ID: c8e3f6a9b2d4
Revises: d9e0f1a2b3c4
Create Date: 2026-10-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8e3f6a9b2d4"
down_revision: str | Sequence[str] | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLS = (
    ("last_status", sa.String(length=16), "上次结果 success/error"),
    ("last_duration_ms", sa.Integer(), "上次耗时（毫秒）"),
    ("last_message", sa.String(length=512), "上次执行摘要 / 错误信息"),
    ("last_run_id", sa.String(length=40), "上次执行的 run_id（对应 ai_run_steps）"),
)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    # 插件表：空库全链重放时可能还没建，直接跳过（建表迁移里已有这些列以外的东西）
    if "ai_workspace_cron" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("ai_workspace_cron")}
    for name, typ, comment in _COLS:
        if name in have:
            continue
        op.add_column(
            "ai_workspace_cron",
            sa.Column(name, typ, nullable=True, comment=comment),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "ai_workspace_cron" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("ai_workspace_cron")}
    for name, _typ, _comment in _COLS:
        if name in have:
            op.drop_column("ai_workspace_cron", name)
