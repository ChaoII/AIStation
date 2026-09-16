"""告警规则作用域扩组：camera_id 可空 + 新增 group_id

Revision ID: d6d5f85952f5
Revises: 2eab490f8488
Create Date: 2026-09-15 14:02:08.372538

说明：autogenerate 会带出大量无关漂移（train_*/ai_*/annotation_* 等），
本文件已手工裁剪为**仅** video_alarm_rules 的最小增量。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6d5f85952f5"
down_revision: str | None = "2eab490f8488"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 显式命名外键，便于 downgrade 精确删除
FK_NAME = "fk_video_alarm_rules_group_id"


def upgrade() -> None:
    """仅变更 video_alarm_rules：camera_id 改可空 + 新增 group_id（FK/索引）。"""
    # 组规则的 camera_id 为空，故放开 NOT NULL
    op.alter_column(
        "video_alarm_rules",
        "camera_id",
        existing_type=sa.INTEGER(),
        nullable=True,
    )
    op.add_column(
        "video_alarm_rules",
        sa.Column("group_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_video_alarm_rules_group_id"),
        "video_alarm_rules",
        ["group_id"],
        unique=False,
    )
    op.create_foreign_key(
        FK_NAME,
        "video_alarm_rules",
        "video_camera_groups",
        ["group_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """回滚：删除 group_id 并恢复 camera_id NOT NULL。

    注意：恢复 NOT NULL 前必须确保表中不存在 camera_id 为 NULL 的行
    （即所有组规则已删除或已回填 camera_id），否则本迁移会因存在 NULL 而失败。
    """
    op.drop_constraint(FK_NAME, "video_alarm_rules", type_="foreignkey")
    op.drop_index(op.f("ix_video_alarm_rules_group_id"), table_name="video_alarm_rules")
    op.alter_column(
        "video_alarm_rules",
        "camera_id",
        existing_type=sa.INTEGER(),
        nullable=False,
    )
    op.drop_column("video_alarm_rules", "group_id")
