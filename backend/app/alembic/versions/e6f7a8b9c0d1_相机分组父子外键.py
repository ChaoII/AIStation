"""video_camera_groups.parent_id 自引用外键（审计 M7）。

历史遗留：``parent_id`` 只有普通整数列、无外键，父分组被删后子分组会成为
「指向不存在父节点」的悬空记录，``traversal_to_tree`` 组树时会直接丢节点
（子分组在界面上凭空消失且占位）。

本迁移：
1. **保留数据**：把悬空（父不存在）与自引用的 ``parent_id`` 置为 NULL（分组本身
   保留并上浮为根节点），使历史数据满足外键约束；
2. 建 ``parent_id`` 索引；
3. 补建自引用外键，``ON DELETE RESTRICT``——应用层 ``delete_group_service`` 已
   前置校验「存在子分组即拒绝」，RESTRICT 作为 DB 级兜底。

幂等：外键/索引均按存在性探测后再建，兼容「先兜底后迁移」与重复执行。
SQLite 不支持 ALTER ADD CONSTRAINT，走 ``batch_alter_table`` 重建表。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.alembic.dialect_compat import is_sqlite

revision: str = "e6f7a8b9c0d1"
down_revision: str | Sequence[str] | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "video_camera_groups"
FK_NAME = "fk_video_camera_groups_parent_id"
IDX_NAME = "ix_video_camera_groups_parent_id"


def _has_table() -> bool:
    return sa.inspect(op.get_bind()).has_table(TABLE)


def _fk_exists() -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(TABLE):
        return False
    return any(
        tuple(fk.get("constrained_columns") or ()) == ("parent_id",)
        for fk in insp.get_foreign_keys(TABLE)
    )


def _index_exists() -> bool:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(TABLE):
        return False
    return IDX_NAME in {idx.get("name") for idx in insp.get_indexes(TABLE)}


def _cleanup_dangling_parents() -> None:
    """把悬空/自引用父节点置 NULL（子分组上浮为根，避免建约束失败）。"""
    # MySQL 不允许 UPDATE 时在子查询中直接读同表，用派生表包裹；
    # PostgreSQL / SQLite 直接子查询即可。
    if op.get_bind().dialect.name == "mysql":
        subquery = f"(SELECT id FROM (SELECT id FROM {TABLE}) AS _t)"
    else:
        subquery = f"(SELECT id FROM {TABLE})"
    op.execute(
        f"UPDATE {TABLE} SET parent_id = NULL "
        f"WHERE parent_id IS NOT NULL AND (parent_id = id OR parent_id NOT IN {subquery})"
    )


def upgrade() -> None:
    if not _has_table():
        return
    _cleanup_dangling_parents()
    if not _index_exists():
        op.create_index(IDX_NAME, TABLE, ["parent_id"], unique=False)
    if _fk_exists():
        return
    if is_sqlite(op.get_bind()):
        with op.batch_alter_table(TABLE) as batch_op:
            batch_op.create_foreign_key(
                FK_NAME, TABLE, ["parent_id"], ["id"], ondelete="RESTRICT"
            )
    else:
        op.create_foreign_key(
            FK_NAME, TABLE, TABLE, ["parent_id"], ["id"], ondelete="RESTRICT"
        )


def downgrade() -> None:
    if not _has_table():
        return
    if _fk_exists():
        if is_sqlite(op.get_bind()):
            with op.batch_alter_table(TABLE) as batch_op:
                batch_op.drop_constraint(FK_NAME, type_="foreignkey")
        else:
            op.drop_constraint(FK_NAME, TABLE, type_="foreignkey")
    if _index_exists():
        op.drop_index(IDX_NAME, table_name=TABLE)
