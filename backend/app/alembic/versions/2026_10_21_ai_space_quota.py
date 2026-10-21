"""个人工作空间：扩容申请表 + 按用户配额覆盖表

Revision ID: d4e5f6a7b8c9
Revises: c0ffee111111
Create Date: 2026-10-21 00:00:00.000000

说明：手写迁移。autogenerate 会因本项目存在大量未被模型覆盖的历史/影子表
（ont_* 等）产生无关 DROP，因此只保留本特性所需变更。
插件模块表（ai_*）可由应用启动 create_all 兜底，此处 ``has_table`` 幂等守卫，
避免空库全链重放（SQLite 回归）失败。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_cols() -> list[sa.Column]:
    """ModelMixin 通用列（与模型一致）。"""
    return [
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String(length=64), nullable=False, unique=True),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.Column("updated_time", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_time", sa.DateTime(), nullable=True),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "ai_space_quota_requests" not in insp.get_table_names():
        op.create_table(
            "ai_space_quota_requests",
            *_base_cols(),
            sa.Column(
                "user_id", sa.Integer(), sa.ForeignKey("sys_user.id", ondelete="CASCADE"),
                nullable=False, comment="申请人ID",
            ),
            sa.Column("target_mb", sa.Integer(), nullable=False, comment="申请目标配额（MB）"),
            sa.Column("reason", sa.String(length=500), nullable=False, server_default="", comment="申请理由"),
            sa.Column("reviewed_by", sa.Integer(), nullable=True, comment="审核人ID"),
            sa.Column("review_note", sa.String(length=500), nullable=False, server_default="", comment="审核备注"),
            sa.Column("review_time", sa.DateTime(), nullable=True, comment="审核时间"),
            comment="个人工作空间扩容申请表",
        )

    if "ai_space_user_quota" not in insp.get_table_names():
        op.create_table(
            "ai_space_user_quota",
            *_base_cols(),
            sa.Column(
                "user_id", sa.Integer(), sa.ForeignKey("sys_user.id", ondelete="CASCADE"),
                nullable=False, unique=True, comment="用户ID",
            ),
            sa.Column("quota_mb", sa.Integer(), nullable=False, comment="该用户生效配额（MB）"),
            sa.Column("updated_by", sa.Integer(), nullable=True, comment="最后修改人ID"),
            comment="个人空间按用户配额覆盖表",
        )


def downgrade() -> None:
    op.drop_table("ai_space_user_quota")
    op.drop_table("ai_space_quota_requests")
