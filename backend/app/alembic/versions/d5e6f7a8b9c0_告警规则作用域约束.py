"""告警规则作用域不变量约束（camera_id 与 group_id 恰有其一）

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-16

应用层（``alarm/service._validate_scope``）已强制，但 DB 层缺失。使用
``NOT VALID`` 添加：既约束后续写入，又不因历史双空/双非空行而失败；
历史非法行由启动校验（``validate_rule_scope_invariant``）发现并告警。
"""
from collections.abc import Sequence

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | Sequence[str] | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_video_alarm_rules_scope_xor"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '{_CONSTRAINT}'
            ) THEN
                ALTER TABLE video_alarm_rules
                ADD CONSTRAINT {_CONSTRAINT}
                CHECK ((camera_id IS NULL) <> (group_id IS NULL)) NOT VALID;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE video_alarm_rules DROP CONSTRAINT IF EXISTS {_CONSTRAINT};")
