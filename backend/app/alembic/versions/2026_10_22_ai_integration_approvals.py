"""AI 集成：调用审批表（敏感能力「先审批后执行」）

Revision ID: d9e0f1a2b3c4
Revises: b7c8d9e0f1a2
Create Date: 2026-10-22 18:00:00.000000

说明：手写迁移（`autogenerate` 会误判大量未被模型覆盖的历史/影子表，产生无关 DROP）。
- 新建 `ai_integration_approvals`：应用开启 `requires_approval` 且能力标记为敏感时，
  调用先落一行 `pending`，管理员批准后执行并回写结果。
- `has_table` 幂等守卫，空库全链重放安全。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9e0f1a2b3c4"
down_revision: str | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "ai_integration_approvals"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if _TABLE in insp.get_table_names():
        return
    op.create_table(
        _TABLE,
        sa.Column("app_id", sa.Integer(), nullable=False, comment="所属应用ID"),
        sa.Column("appid", sa.String(length=64), nullable=False, comment="应用标识（冗余）"),
        sa.Column("capability", sa.String(length=64), nullable=False, comment="能力码"),
        sa.Column("category", sa.String(length=16), nullable=False, comment="品类"),
        sa.Column("payload", sa.JSON(), nullable=True, comment="能力入参（已脱敏）"),
        sa.Column("status", sa.String(length=16), nullable=False, comment="状态: pending/approved/rejected/failed"),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True, comment="审批时间"),
        sa.Column("reviewed_by", sa.Integer(), nullable=True, comment="审批人用户ID"),
        sa.Column("review_note", sa.String(length=255), nullable=True, comment="审批意见"),
        sa.Column("result", sa.JSON(), nullable=True, comment="执行结果"),
        sa.Column("error", sa.String(length=255), nullable=True, comment="执行错误"),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="申请时间"),
        sa.ForeignKeyConstraint(["app_id"], ["ai_integration_apps.id"]),
        sa.PrimaryKeyConstraint("id"),
        comment="AI 集成调用审批表",
    )
    op.create_index(op.f(f"ix_{_TABLE}_app_id"), _TABLE, ["app_id"], unique=False)
    op.create_index(op.f(f"ix_{_TABLE}_status"), _TABLE, ["status"], unique=False)
    op.create_index(op.f(f"ix_{_TABLE}_created_time"), _TABLE, ["created_time"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if _TABLE in insp.get_table_names():
        op.drop_table(_TABLE)
