"""AI 集成开放平台：应用归属用户(owner_user_id) + 用户自助申请(app applies)

Revision ID: c2d3e4f5a6b7
Revises: f3a4b5c6d7e8
Create Date: 2026-10-29 00:00:00.000000

说明：手写迁移。autogenerate 会因本项目存在大量未被模型覆盖的历史/影子表
（ont_* 等）产生无关 DROP，因此只保留本特性所需变更。
- 给 ``ai_integration_apps`` 增列 ``owner_user_id``（FK sys_user，可空：null=平台级/A，非空=用户自助B）。
- 新建 ``ai_integration_app_applies``（用户自助申请单，模式 B）。
均用 ``has_column`` / ``has_table`` 幂等守卫，避免空库全链重放（SQLite 回归）失败。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.alembic.dialect_compat import is_sqlite

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. 应用表：增 owner_user_id
    if "ai_integration_apps" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("ai_integration_apps")}
        if "owner_user_id" not in cols:
            op.add_column(
                "ai_integration_apps",
                sa.Column("owner_user_id", sa.Integer(), nullable=True, comment="归属用户ID（null=平台级/管理员分配A；非空=用户自助申请B）"),
            )
            # SQLite 不支持 ALTER TABLE ADD CONSTRAINT，必须 batch 重建（空库全链重放会走到）
            if is_sqlite(bind):
                with op.batch_alter_table("ai_integration_apps") as batch_op:
                    batch_op.create_foreign_key(
                        "fk_ai_integration_apps_owner_user_id",
                        "sys_user",
                        ["owner_user_id"],
                        ["id"],
                        onupdate="CASCADE",
                        ondelete="SET NULL",
                    )
            else:
                op.create_foreign_key(
                    "fk_ai_integration_apps_owner_user_id",
                    "ai_integration_apps",
                    "sys_user",
                    ["owner_user_id"],
                    ["id"],
                    onupdate="CASCADE",
                    ondelete="SET NULL",
                )
            op.create_index(
                op.f("ix_ai_integration_apps_owner_user_id"),
                "ai_integration_apps",
                ["owner_user_id"],
                unique=False,
            )

    # 2. 用户自助申请表
    if "ai_integration_app_applies" not in insp.get_table_names():
        op.create_table(
            "ai_integration_app_applies",
            sa.Column("app_id", sa.Integer(), nullable=True, comment="批准后生成的应用ID"),
            sa.Column("applicant_id", sa.Integer(), nullable=False, comment="申请者用户ID（owner_user_id）"),
            sa.Column("name", sa.String(length=128), nullable=False, comment="申请的应用名称（唯一）"),
            sa.Column("description", sa.Text(), nullable=True, comment="应用描述"),
            sa.Column("reason", sa.String(length=255), nullable=True, comment="申请说明/用途"),
            sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment="申请的能力码列表（须不超出申请者角色权限）"),
            sa.Column("channels", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="出口控制 {能力码: [rest,mcp]}，null=全部支持"),
            sa.Column("apply_status", sa.String(length=16), nullable=False, comment="审批状态: pending/approved/rejected"),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True, comment="审核时间"),
            sa.Column("reviewed_by", sa.Integer(), nullable=True, comment="审核人用户ID"),
            sa.Column("review_note", sa.String(length=255), nullable=True, comment="审核意见/驳回原因"),
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
            sa.Column("uuid", sa.String(length=64), nullable=False, comment="UUID全局唯一标识"),
            sa.Column("status", sa.String(length=10), nullable=False, comment="状态(0:正常 1:禁用)"),
            sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, comment="是否已删除(0:未删除 1:已删除)"),
            sa.Column("deleted_time", sa.DateTime(), nullable=True, comment="删除时间"),
            sa.Column("created_id", sa.Integer(), nullable=True, comment="创建人ID"),
            sa.Column("updated_id", sa.Integer(), nullable=True, comment="更新人ID"),
            sa.Column("deleted_id", sa.Integer(), nullable=True, comment="删除人ID"),
            sa.ForeignKeyConstraint(["app_id"], ["ai_integration_apps.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["applicant_id"], ["sys_user.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["deleted_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            comment="AI 集成应用自助申请表",
        )
        op.create_index(op.f("ix_ai_integration_app_applies_applicant_id"), "ai_integration_app_applies", ["applicant_id"], unique=False)
        op.create_index(op.f("ix_ai_integration_app_applies_created_time"), "ai_integration_app_applies", ["created_time"], unique=False)
        op.create_index(op.f("ix_ai_integration_app_applies_id"), "ai_integration_app_applies", ["id"], unique=False)
        op.create_index(op.f("ix_ai_integration_app_applies_apply_status"), "ai_integration_app_applies", ["apply_status"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "ai_integration_app_applies" in insp.get_table_names():
        op.drop_table("ai_integration_app_applies")

    if "ai_integration_apps" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("ai_integration_apps")}
        if "owner_user_id" in cols:
            op.drop_index(op.f("ix_ai_integration_apps_owner_user_id"), table_name="ai_integration_apps")
            # 同 upgrade：SQLite 的 DROP CONSTRAINT 也要走 batch 重建
            if is_sqlite(bind):
                with op.batch_alter_table("ai_integration_apps") as batch_op:
                    batch_op.drop_constraint(
                        "fk_ai_integration_apps_owner_user_id", type_="foreignkey"
                    )
                    batch_op.drop_column("owner_user_id")
            else:
                op.drop_constraint("fk_ai_integration_apps_owner_user_id", "ai_integration_apps", type_="foreignkey")
                op.drop_column("ai_integration_apps", "owner_user_id")
