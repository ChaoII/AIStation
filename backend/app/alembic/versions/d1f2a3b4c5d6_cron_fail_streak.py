"""定时任务补「连续失败 / 自动停用」两列

连续失败到上限自动停用，避免一条坏配置每天准时烧模型调用。

Revision ID: d1f2a3b4c5d6
Revises: c8e3f6a9b2d4
Create Date: 2026-10-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "c8e3f6a9b2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLS = (
    (
        "fail_streak",
        sa.Integer(),
        "0",
        "连续失败次数（成功清零）",
    ),
    (
        "auto_disabled",
        sa.Boolean(),
        "false",
        "是否因连续失败被自动停用",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "ai_workspace_cron" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("ai_workspace_cron")}
    for name, typ, default, comment in _COLS:
        if name in have:
            continue
        op.add_column(
            "ai_workspace_cron",
            sa.Column(name, typ, nullable=False, server_default=sa.text(default), comment=comment),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "ai_workspace_cron" not in insp.get_table_names():
        return
    have = {c["name"] for c in insp.get_columns("ai_workspace_cron")}
    for name, _typ, _default, _comment in _COLS:
        if name in have:
            op.drop_column("ai_workspace_cron", name)
