"""告警记录按时间查询索引

Revision ID: c4d5e6f7a8b9
Revises: a3f3956bb77b
Create Date: 2026-09-16

告警记录列表/实时接口按 ``alarm_time DESC`` 排序与过滤，原先无该列索引，
数据量增大后退化为全表排序。补齐索引（与模型 ``index=True`` 对齐）。
"""
from collections.abc import Sequence

from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str | Sequence[str] | None = "a3f3956bb77b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_video_alarm_records_alarm_time"


def upgrade() -> None:
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {_INDEX} ON video_alarm_records (alarm_time);"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX};")
