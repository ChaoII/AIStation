"""AI 集成 P2/P3：开放面资源归属列（ai_agents / train_tasks）

Revision ID: b7c8d9e0f1a2
Revises: a9b8c7d6e5f4
Create Date: 2026-10-22 12:00:00.000000

说明：手写迁移（`autogenerate` 会误判大量未被模型覆盖的历史/影子表，产生无关 DROP）。
- 为 `ai_agents` 与 `train_tasks` 各加一列 `source_app_id`（可空，FK `ai_integration_apps.id`），
  用于「开放平台创建的资源归属哪个集成应用」；空值 = 平台内部用户创建。
- 一律 `has_column` 探测后加列，空库全链重放 / 重复执行均安全；
- `ai_agents` 由插件模块建表，空库重放时表可能尚不存在 → 用 `has_table` 守卫跳过。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a9b8c7d6e5f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("ai_agents", "train_tasks")


def _columns(insp, table: str) -> set[str]:
    """返回表的列名集合（表不存在返回空集）。"""
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _index_names(insp, table: str) -> set[str]:
    """返回表的索引名集合（表不存在返回空集）。"""
    if table not in insp.get_table_names():
        return set()
    return {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    for table in _TABLES:
        if table not in tables:
            continue
        if "source_app_id" in _columns(insp, table):
            continue
        op.add_column(
            table,
            sa.Column(
                "source_app_id",
                sa.Integer(),
                nullable=True,
                comment="开放平台归属应用ID（空=平台内部创建）",
            ),
        )
        op.create_index(
            op.f(f"ix_{table}_source_app_id"), table, ["source_app_id"], unique=False
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in _TABLES:
        if table not in insp.get_table_names():
            continue
        if "source_app_id" not in _columns(insp, table):
            continue
        idx = op.f(f"ix_{table}_source_app_id")
        if idx in _index_names(insp, table):
            op.drop_index(idx, table_name=table)
        op.drop_column(table, "source_app_id")
