"""定时任务自动停用 → 管理员通知（系统参数）

新增一个开关参数 `ai_cron_notify_channels`（email,webhook），
收件人/凭证沿用通用告警参数 notify_admin_email / notify_webhook_default_url。

Revision ID: e2a3b4c5d6e7
Revises: d1f2a3b4c5d6
Create Date: 2026-10-25
"""
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "e2a3b4c5d6e7"
down_revision: str | Sequence[str] | None = "d1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KEY = "ai_cron_notify_channels"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sys_param" not in insp.get_table_names():
        return
    exists = bind.execute(
        sa.text("SELECT id FROM sys_param WHERE config_key = :k"), {"k": _KEY}
    ).fetchall()
    if exists:
        return
    now = datetime.now()
    bind.execute(
        sa.text(
            "INSERT INTO sys_param "
            "(uuid, status, description, created_time, updated_time, is_deleted, "
            " config_name, config_key, config_value, config_type) "
            "VALUES (:uuid, '0', :desc, :now, :now, false, :name, :key, :val, false)"
        ),
        {
            "uuid": f"cronnotify{int(now.timestamp())}",
            "desc": "定时任务连续失败自动停用时的通知通道（email,webhook；空=关闭）",
            "now": now,
            "name": "定时任务自动停用通知-通道",
            "key": _KEY,
            "val": "email,webhook",
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sys_param" not in insp.get_table_names():
        return
    bind.execute(sa.text("DELETE FROM sys_param WHERE config_key = :k"), {"k": _KEY})
