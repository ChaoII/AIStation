"""告警规则作用域不变量约束（camera_id 与 group_id 恰有其一）

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-16

应用层（``alarm/service._validate_scope``）已强制，但 DB 层缺失。使用
``NOT VALID`` 添加：既约束后续写入，又不因历史双空/双非空行而失败；
历史非法行由启动校验（``validate_rule_scope_invariant``）发现并告警。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.alembic.dialect_compat import is_postgres, is_sqlite

revision: str = "d5e6f7a8b9c0"
down_revision: str | Sequence[str] | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_video_alarm_rules_scope_xor"


_CHECK_EXPR = "(camera_id IS NULL) <> (group_id IS NULL)"


def _constraint_exists() -> bool:
    """探测 CHECK 约束是否已存在（幂等）。"""
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("video_alarm_rules"):
        return False
    return _CONSTRAINT in {
        ck.get("name") for ck in insp.get_check_constraints("video_alarm_rules")
    }


def upgrade() -> None:
    if _constraint_exists():
        return
    bind = op.get_bind()
    if is_postgres(bind):
        # PostgreSQL：DO 块内按 pg_constraint 探测；NOT VALID 使历史脏行不阻塞建约束
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = '{_CONSTRAINT}'
                ) THEN
                    ALTER TABLE video_alarm_rules
                    ADD CONSTRAINT {_CONSTRAINT}
                    CHECK ({_CHECK_EXPR}) NOT VALID;
                END IF;
            END
            $$;
            """
        )
        return
    if is_sqlite(bind):
        # SQLite：ADD CONSTRAINT 需 batch 重建表
        with op.batch_alter_table("video_alarm_rules") as batch_op:
            batch_op.create_check_constraint(_CONSTRAINT, _CHECK_EXPR)
        return
    # MySQL：无 NOT VALID，直接添加（若历史存在脏行，用户需先清理）
    op.execute(
        f"ALTER TABLE video_alarm_rules ADD CONSTRAINT {_CONSTRAINT} CHECK ({_CHECK_EXPR})"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if is_sqlite(bind) and _constraint_exists():
        with op.batch_alter_table("video_alarm_rules") as batch_op:
            batch_op.drop_constraint(_CONSTRAINT, type_="check")
        return
    op.execute(f"ALTER TABLE video_alarm_rules DROP CONSTRAINT IF EXISTS {_CONSTRAINT};")
