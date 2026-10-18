"""三表统一 trigger/trigger_args 列（新增 + 规范化回填 + 删旧列）

Revision ID: f6b7c8d9e0a1
Revises: e2f3a4b5c6d7
Create Date: 2026-10-18 10:00:00.000000

说明（**手写迁移**，本项目禁用 autogenerate：dev 库有 400+ 历史/影子表，
autogenerate 会把它们判成待 DROP）：
- 覆盖三张表，把旧 cron 列搬迁为统一的 `trigger` + `trigger_args`（规格 §4.4）：
    ai_workspace_cron.cron        → trigger='cron' + trigger_args
    ai_workflow_schedules.cron    → 同上
    train_schedules.cron_expr     → 同上
- **不做静默语义改写**：可等值转换的写回规范化值；6 段秒位非 0 / 7 段带年 / 解析失败 /
  空值一律**跳过并逐条打印迁移日志**（trigger_args 留空，由列表接口标为「表达式需人工确认」）。
- 规范化复用 `app.utils.trigger_migration.normalize_legacy`（其内部复用 `TriggerUtil`），
  本迁移**不复制**周字段映射表。
- 插件表（`ai_workspace_cron` / `ai_workflow_schedules`）不由迁移链创建，空库全链重放
  （SQLite 回归）时可能不存在 → 操作前一律 `sa.inspect(bind).has_table()` 判定。
- `downgrade()` 反向重建旧列并从 `trigger_args` 回填；`?`→`*` 与段数裁剪属等价变换，
  回滚得到的是规范化后的表达式（非原始文本）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.utils.trigger_migration import normalize_legacy

revision: str = "f6b7c8d9e0a1"
down_revision: str | None = "e2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (表名, 旧列名, 旧列长度, 旧列是否非空)——降级时按此还原旧列
LEGACY_COLUMNS: tuple[tuple[str, str, int, bool], ...] = (
    ("ai_workspace_cron", "cron", 128, True),
    ("ai_workflow_schedules", "cron", 128, True),
    ("train_schedules", "cron_expr", 64, False),
)

TRIGGER_COMMENT = "触发类型 cron/interval/date/now"
TRIGGER_ARGS_COMMENT = "触发参数（cron 5 段 / interval JSON / date 时间，now 为空）"


def _column_names(bind, table: str) -> set[str]:
    """当前表的列名集合（每次现取，避免用陈旧快照判断后续 DDL）。"""
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _add_trigger_columns(table: str, columns: set[str]) -> None:
    """新增 `trigger`（非空，默认 `cron`）与 `trigger_args`（可空）。"""
    if "trigger" not in columns:
        op.add_column(
            table,
            sa.Column(
                "trigger",
                sa.String(length=16),
                nullable=False,
                server_default="cron",
                comment=TRIGGER_COMMENT,
            ),
        )
    if "trigger_args" not in columns:
        op.add_column(
            table,
            sa.Column("trigger_args", sa.Text(), nullable=True, comment=TRIGGER_ARGS_COMMENT),
        )


def _backfill_from_legacy(bind, table: str, legacy_col: str) -> list[str]:
    """逐行把旧 cron 列回填到 `trigger_args`，返回跳过日志（中文，供 print 与测试断言）。

    可等值转换的行写回规范化后的 5 段；其余行**保持 trigger_args 为空**并记日志，
    绝不写一个"看起来能跑"的表达式（那才是静默语义改写）。
    """
    logs: list[str] = []
    rows = bind.execute(sa.text(f"SELECT id, {legacy_col} FROM {table}")).fetchall()
    for row_id, legacy in rows:
        _trigger, args, skip = normalize_legacy(legacy)
        if skip:
            logs.append(f"{table}#{row_id}：{skip}")
            continue
        bind.execute(
            sa.text(
                f"UPDATE {table} SET trigger = :trigger, trigger_args = :args WHERE id = :row_id"
            ),
            {"trigger": "cron", "args": args, "row_id": row_id},
        )
    return logs


def _restore_legacy_from_args(bind, table: str, legacy_col: str) -> int:
    """降级：把 `trigger_args` 反向写回旧列，返回回填行数。

    非 `cron` 触发（interval/date/now）在旧列里没有对应值 → 写空串，
    以满足旧列的非空约束（`train_schedules.cron_expr` 为 NOT NULL）。
    """
    rows = bind.execute(sa.text(f"SELECT id, trigger, trigger_args FROM {table}")).fetchall()
    for row_id, trigger, args in rows:
        value = args if trigger == "cron" and args else ""
        bind.execute(
            sa.text(f"UPDATE {table} SET {legacy_col} = :value WHERE id = :row_id"),
            {"value": value, "row_id": row_id},
        )
    return len(rows)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, legacy_col, _length, _nullable in LEGACY_COLUMNS:
        if not inspector.has_table(table):
            # 插件表可能不在迁移链里（空库全链重放）：跳过，交由模型 create_all 建表
            continue
        columns = _column_names(bind, table)
        _add_trigger_columns(table, columns)
        if legacy_col in columns:
            for log in _backfill_from_legacy(bind, table, legacy_col):
                print(f"[trigger 迁移] {log}")
            op.drop_column(table, legacy_col)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, legacy_col, length, nullable in LEGACY_COLUMNS:
        if not inspector.has_table(table):
            continue
        columns = _column_names(bind, table)
        if legacy_col not in columns:
            # 先按可空新增（表里可能已有数据，PG 不允许无默认值直接加非空列）
            op.add_column(
                table,
                sa.Column(
                    legacy_col,
                    sa.String(length=length),
                    nullable=True,
                    comment="回滚重建的旧 cron 列",
                ),
            )
        if {"trigger", "trigger_args"} <= columns:
            restored = _restore_legacy_from_args(bind, table, legacy_col)
            print(f"[trigger 迁移] 降级回填 {table}.{legacy_col}：{restored} 行")
        if not nullable and bind.dialect.name != "sqlite":
            # 旧列原本非空：回填后再收紧（此时已无 NULL）。
            # SQLite 不支持 ALTER COLUMN SET NOT NULL（需整表重建），故仅在 PG/MySQL 上收紧。
            op.alter_column(table, legacy_col, nullable=False)
        for column in ("trigger_args", "trigger"):
            if column in columns:
                op.drop_column(table, column)
