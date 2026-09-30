"""训练模块：模型引用列放宽为可空

Revision ID: tk1m0d2l4r6
Revises: b3c4d5e6f7a8
Create Date: 2026-10-01

背景
----
2026-07 的数据事故误删了一批模型行，留下 **47 条悬空引用**（仓库指向已删版本、
任务/评估/预测指向已删模型）。其中 ``train_model_repos.latest_version_id`` 与
``train_tasks.model_repo_id`` 本来就可空，直接置 NULL 即可；但

- ``train_evals.model_repo_id``
- ``train_predicts.model_id``
- ``train_predicts.model_repo_id``

声明为 ``NOT NULL``，**结构上无法表达"引用的模型已被删除"这一合法状态**——这类行
只能卡在指向一个不存在的 id 上，既不能修复也不能如实记录。

顺带说明字段名有误导：``TrainTask.model_repo_id`` / ``TrainEval.model_repo_id``
存的其实是**模型版本行 id**（``train_models.id``），不是仓库 id。本迁移只改可空性，
不动字段语义与类型。

改动
----
仅放宽可空约束（``SET NOT NULL`` → 去掉），属**放宽**而非收紧，方向安全：
不会让既有数据非法，也不会改变任何查询的既有行为（NULL 行原本就走"取不到就显示
占位"的分支）。

回滚时需先处理 NULL 行（``downgrade`` 里已显式报错提示，而不是默默丢数据）。
"""

from collections.abc import Sequence

from alembic import op

from app.alembic.dialect_compat import is_postgres

# revision identifiers, used by Alembic.
revision: str = "tk1m0d2l4r6"
down_revision: str | Sequence[str] | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: (表名, 列名) —— 这些列存的其实是**模型版本行 id**（train_models.id）
_TARGETS: tuple[tuple[str, str], ...] = (
    ("train_evals", "model_repo_id"),
    ("train_predicts", "model_id"),
    ("train_predicts", "model_repo_id"),
)


def upgrade() -> None:
    """去掉三个模型引用列的 NOT NULL，让"模型已删除"可被如实记录。

    SQLite 不支持 ``ALTER COLUMN ... DROP NOT NULL``（需重建表），但测试库走
    SQLAlchemy ``create_all`` 建表，列定义本就来自 model.py 的 ``nullable=True``，
    所以这里跳过 SQLite 不影响测试。
    """
    bind = op.get_bind()
    if not is_postgres(bind):
        return
    for table, column in _TARGETS:
        op.execute(f'ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL')


def downgrade() -> None:
    """加回 NOT NULL。

    ⚠️ 若已有 NULL 行（悬空引用被置空后），直接加回会失败。先查一遍并报出具体行，
    而不是让它抛一条看不懂的 PG 错误，或更糟——默默把 NULL 填成某个猜测值。
    """
    bind = op.get_bind()
    if not is_postgres(bind):
        return

    null_rows: list[str] = []
    for table, column in _TARGETS:
        # 表名/列名来自本文件的模块级常量 _TARGETS，不是用户输入，无注入面
        n = bind.exec_driver_sql(
            f"SELECT count(*) FROM {table} WHERE {column} IS NULL"  # noqa: S608
        ).scalar()
        if n:
            null_rows.append(f"{table}.{column}={n} 行")
    if null_rows:
        raise RuntimeError(
            "以下列存在 NULL 行，无法加回 NOT NULL（请先决定这些引用如何处置）："
            + "；".join(null_rows)
        )

    for table, column in _TARGETS:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL")
