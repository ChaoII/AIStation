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

from app.alembic.dialect_compat import is_sqlite

# revision identifiers, used by Alembic.
revision: str = "d6d5f85952f5"
down_revision: str | None = "2eab490f8488"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 显式命名外键，便于 downgrade 精确删除
FK_NAME = "fk_video_alarm_rules_group_id"


def _has_column(table: str, column: str) -> bool:
    """列存在探测：兼容「先重启兜底补列、后跑迁移」的顺序（避免 DuplicateColumn）。"""
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return column in {col["name"] for col in insp.get_columns(table)}


def _has_index(table: str, index_name: str) -> bool:
    """索引存在探测（兜底补列只加列、不加索引，故需按需创建）。"""
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return index_name in {idx["name"] for idx in insp.get_indexes(table)}


def _has_foreign_key(table: str, fk_name: str) -> bool:
    """外键存在探测（幂等创建 FK）。"""
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return fk_name in {fk["name"] for fk in insp.get_foreign_keys(table)}


def _upgrade_sqlite() -> None:
    """SQLite 分支：ALTER COLUMN / ADD CONSTRAINT 需走 batch 模式（重建表）。"""
    add_group = not _has_column("video_alarm_rules", "group_id")
    add_index = not _has_index("video_alarm_rules", op.f("ix_video_alarm_rules_group_id"))
    add_fk = not _has_foreign_key("video_alarm_rules", FK_NAME)
    with op.batch_alter_table("video_alarm_rules") as batch_op:
        batch_op.alter_column(
            "camera_id",
            existing_type=sa.INTEGER(),
            nullable=True,
        )
        if add_group:
            batch_op.add_column(sa.Column("group_id", sa.Integer(), nullable=True))
        if add_index:
            batch_op.create_index(
                op.f("ix_video_alarm_rules_group_id"),
                ["group_id"],
                unique=False,
            )
        if add_fk:
            batch_op.create_foreign_key(
                FK_NAME,
                "video_camera_groups",
                ["group_id"],
                ["id"],
                ondelete="SET NULL",
            )


def upgrade() -> None:
    """仅变更 video_alarm_rules：camera_id 改可空 + 新增 group_id（FK/索引）。"""
    # SQLite 不支持 ALTER COLUMN / ADD CONSTRAINT，改走 batch 重建表
    if is_sqlite(op.get_bind()):
        _upgrade_sqlite()
        return
    # 组规则的 camera_id 为空，故放开 NOT NULL（重复执行设置 nullable=True 亦幂等）
    op.alter_column(
        "video_alarm_rules",
        "camera_id",
        existing_type=sa.INTEGER(),
        nullable=True,
    )
    # group_id 可能已由启动兜底补列添加
    if not _has_column("video_alarm_rules", "group_id"):
        op.add_column(
            "video_alarm_rules",
            sa.Column("group_id", sa.Integer(), nullable=True),
        )
    if not _has_index("video_alarm_rules", op.f("ix_video_alarm_rules_group_id")):
        op.create_index(
            op.f("ix_video_alarm_rules_group_id"),
            "video_alarm_rules",
            ["group_id"],
            unique=False,
        )
    if not _has_foreign_key("video_alarm_rules", FK_NAME):
        op.create_foreign_key(
            FK_NAME,
            "video_alarm_rules",
            "video_camera_groups",
            ["group_id"],
            ["id"],
            ondelete="SET NULL",
        )


def _assert_no_null_camera_id(bind) -> None:
    """回滚前置校验：存在 camera_id 为 NULL 的组规则时明确拒绝（L3）。

    直接 ALTER 恢复 NOT NULL 会抛出难懂的数据库错误；此处提前检测并给出可操作提示。
    """
    insp = sa.inspect(bind)
    if not insp.has_table("video_alarm_rules"):
        return
    if "camera_id" not in {col["name"] for col in insp.get_columns("video_alarm_rules")}:
        return
    nulls = bind.execute(
        sa.text("SELECT COUNT(*) FROM video_alarm_rules WHERE camera_id IS NULL")
    ).scalar()
    if nulls:
        raise RuntimeError(
            f"无法回滚 d6d5f85952f5：video_alarm_rules 仍有 {nulls} 行 camera_id 为 NULL"
            "（组规则）。请先删除或改绑这些组规则，再执行 downgrade。"
        )


def _downgrade_sqlite() -> None:
    """SQLite 分支：ALTER/删约束需 batch 重建表。"""
    has_fk = _has_foreign_key("video_alarm_rules", FK_NAME)
    has_idx = _has_index("video_alarm_rules", op.f("ix_video_alarm_rules_group_id"))
    has_group = _has_column("video_alarm_rules", "group_id")
    with op.batch_alter_table("video_alarm_rules") as batch_op:
        if has_fk:
            batch_op.drop_constraint(FK_NAME, type_="foreignkey")
        if has_idx:
            batch_op.drop_index(op.f("ix_video_alarm_rules_group_id"))
        batch_op.alter_column(
            "camera_id",
            existing_type=sa.INTEGER(),
            nullable=False,
        )
        if has_group:
            batch_op.drop_column("group_id")


def downgrade() -> None:
    """回滚：删除 group_id 并恢复 camera_id NOT NULL。

    注意：恢复 NOT NULL 前必须确保表中不存在 camera_id 为 NULL 的行
    （即所有组规则已删除或已回填 camera_id），否则本迁移会因存在 NULL 而失败。
    """
    bind = op.get_bind()
    _assert_no_null_camera_id(bind)
    if is_sqlite(bind):
        _downgrade_sqlite()
        return
    if _has_foreign_key("video_alarm_rules", FK_NAME):
        op.drop_constraint(FK_NAME, "video_alarm_rules", type_="foreignkey")
    if _has_index("video_alarm_rules", op.f("ix_video_alarm_rules_group_id")):
        op.drop_index(op.f("ix_video_alarm_rules_group_id"), table_name="video_alarm_rules")
    op.alter_column(
        "video_alarm_rules",
        "camera_id",
        existing_type=sa.INTEGER(),
        nullable=False,
    )
    if _has_column("video_alarm_rules", "group_id"):
        op.drop_column("video_alarm_rules", "group_id")
