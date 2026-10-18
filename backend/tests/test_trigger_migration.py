"""触发列统一迁移（A6）：迁移助手逻辑 + **真实 DDL 路径** + 迁移源码结构约束。

覆盖三条链路：
1. 助手逻辑 `normalize_legacy`（含 7 段年份通配的等值转换）；
2. **真实执行** `upgrade()` / `downgrade()`：在临时 SQLite 库上走
   add_column → 逐行回填 → drop_column 与反向重建，断言列与数据（不依赖 dev PG 库、不依赖一次性探针）；
3. 迁移模块的结构约束（revision 链、目标表、复用统一层、不复制周字段映射表）。
"""

import inspect
import sqlite3
from importlib import import_module
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

VERSIONS_DIR = Path(__file__).parent.parent / "app" / "alembic" / "versions"

#: 本次迁移的 revision（与 `2026_10_18_unify_trigger_columns.py` 一致）
REVISION = "f6b7c8d9e0a1"
#: 迁移链尾（A6 之前的 head），down_revision 必须指向它
PARENT_REVISION = "e2f3a4b5c6d7"

#: SQLite < 3.35 不支持 `ALTER TABLE … DROP COLUMN`（真实 DDL 测试需要）
requires_drop_column = pytest.mark.skipif(
    tuple(int(part) for part in sqlite3.sqlite_version.split(".")[:2]) < (3, 35),
    reason="SQLite 版本过低，不支持 DROP COLUMN",
)


# --------------------------------------------------------------------------- 基础设施


def _migration_path() -> Path:
    """按 revision 常量定位迁移文件（本仓库用「日期前缀」命名，故按内容而非文件名匹配）。"""
    matches = [
        path
        for path in sorted(VERSIONS_DIR.glob("*.py"))
        if f'revision: str = "{REVISION}"' in path.read_text(encoding="utf-8")
    ]
    assert len(matches) == 1, f"期望唯一迁移文件: {matches}"
    return matches[0]


def _migration_module():
    """导入迁移模块（与 test_migration_replay 同风格）。"""
    return import_module(f"app.alembic.versions.{_migration_path().stem}")


def _run_migration(engine: sa.Engine, monkeypatch, func_name: str) -> None:
    """在给定引擎上**真实执行**迁移的 `upgrade()` / `downgrade()`。

    Alembic 的 `op` 是模块级代理，这里把迁移模块里的 `op` 换成绑定到该连接的
    `Operations`（与 `alembic upgrade` 运行时同一条路径：`op.get_bind()` 返回该连接）。
    """
    migration = _migration_module()
    with engine.begin() as conn:
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(conn)))
        getattr(migration, func_name)()


def _columns(engine: sa.Engine, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(engine).get_columns(table)}


def _trigger_rows(engine: sa.Engine, table: str) -> dict:
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT id, trigger, trigger_args FROM {table}"))
        return {row.id: (row.trigger, row.trigger_args) for row in rows}


def _legacy_rows(engine: sa.Engine, table: str, column: str) -> dict:
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT id, {column} FROM {table}"))
        return {row.id: getattr(row, column) for row in rows}


def _legacy_engine() -> sa.Engine:
    """临时 SQLite 库：三张旧表 + 旧列 + 覆盖各种形态的数据。

    `StaticPool` 保证多次 `engine.begin()` 用的是同一条内存连接（DDL/数据得以保留）。
    """
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE ai_workspace_cron (id INTEGER PRIMARY KEY, cron VARCHAR(128))")
        )
        conn.execute(
            text("CREATE TABLE ai_workflow_schedules (id INTEGER PRIMARY KEY, cron VARCHAR(128))")
        )
        conn.execute(
            text(
                "CREATE TABLE train_schedules "
                "(id INTEGER PRIMARY KEY, cron_expr VARCHAR(64) NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO ai_workspace_cron (id, cron) VALUES "
                "(1, '0 9 * * 1'), "  # 5 段：周字段数字 → 星期名
                "(2, '0 0 9 ? * ?'), "  # 6 段秒位 0 + Quartz `?`
                "(3, '30 * * * * *'), "  # 6 段秒位非 0 → 跳过
                "(4, '0 0 9 * * * 2030'), "  # 7 段带具体年份 → 跳过
                "(5, '0 0 9 * * * ?'), "  # 7 段年份通配 → 裁掉末段
                "(6, '0 9 ? * ?')"  # 5 段含 `?` → `*`
            )
        )
        conn.execute(text("INSERT INTO ai_workflow_schedules (id, cron) VALUES (1, '0 0 9 * * *')"))
        conn.execute(
            text(
                "INSERT INTO train_schedules (id, cron_expr) VALUES "
                "(1, '0 2 * * 0'), "  # 5 段：周日
                "(2, '0 9 32 * *')"  # 日字段超范围 → 解析失败，跳过
            )
        )
    return engine


# --------------------------------------------------------------------------- 助手逻辑


def test_migration_helper_normalizes_and_skips_unsafe(test_client):
    """迁移助手：5 段规范化；6 段秒位非 0 / 7 段带年 → 跳过并返回日志。"""
    from app.utils.trigger_migration import normalize_legacy

    assert normalize_legacy("0 9 * * 1") == ("cron", "0 9 * * mon", None)
    assert normalize_legacy("0 0 9 * * *") == ("cron", "0 9 * * *", None)
    trig, args, skip = normalize_legacy("30 * * * * *")
    assert skip and "秒" in skip
    trig, args, skip = normalize_legacy("0 0 9 * * * 2030")
    assert skip and "年" in skip


def test_normalize_legacy_tolerates_quartz_question_mark():
    """迁移路径对 Quartz 的 `?` 容错（→ `*`）：只读旧数据，不做静默语义改写之外的处理。"""
    from app.utils.trigger_migration import normalize_legacy

    assert normalize_legacy("0 9 ? * ?") == ("cron", "0 9 * * *", None)
    # 6 段（秒位为 0）+ `?` 同时出现时，先去首段再容错
    assert normalize_legacy("0 0 9 ? * ?") == ("cron", "0 9 * * *", None)


def test_normalize_legacy_strips_wildcard_year_field():
    """7 段且末段（年份）为 `*` / `?` → 与「无年份」等价，裁掉该段继续规范化。"""
    from app.utils.trigger_migration import normalize_legacy

    assert normalize_legacy("0 0 9 * * * *") == ("cron", "0 9 * * *", None)
    assert normalize_legacy("0 0 9 * * * ?") == ("cron", "0 9 * * *", None)
    # 裁掉年份后周字段仍按统一口径映射
    assert normalize_legacy("0 0 9 * * 1 *") == ("cron", "0 9 * * mon", None)
    # 带具体年份一律拒绝（不做"猜年份"的语义改写）
    trigger, args, skip = normalize_legacy("0 0 9 * * * 2026")
    assert (trigger, args) == ("cron", None)
    assert skip and "年" in skip


def test_normalize_legacy_skips_empty_and_invalid():
    """空值/无法规范化的旧值 → 跳过并给出中文原因（trigger_args 留空待人工确认）。"""
    from app.utils.trigger_migration import normalize_legacy

    for value in (None, "", "   "):
        trigger, args, skip = normalize_legacy(value)
        assert (trigger, args) == ("cron", None)
        assert skip and "空" in skip

    for value in ("0 9 32 * *", "0 9 * *", "0 9 * * mon tue"):
        trigger, args, skip = normalize_legacy(value)
        assert (trigger, args) == ("cron", None)
        assert skip


def test_normalize_legacy_matches_unified_layer_for_five_fields():
    """5 段一律与 `TriggerUtil.normalize_cron` 同源（口径唯一的实断言，而非文本比对）。"""
    from app.utils.trigger_migration import normalize_legacy
    from app.utils.trigger_util import TriggerUtil

    for expr in ("0 9 * * 1-5", "0 9 * * 0-6", "0 9 * * 7", "*/5 9 1,15 * *", "0 9 * * sun"):
        assert normalize_legacy(expr) == ("cron", TriggerUtil.normalize_cron(expr), None)


# --------------------------------------------------------------------------- 真实 DDL 路径


@requires_drop_column
def test_upgrade_adds_columns_backfills_and_drops_legacy(monkeypatch, capsys):
    """`upgrade()`：新增两列 → 逐行规范化回填（跳过的行留空并打日志）→ 删旧列。"""
    engine = _legacy_engine()
    _run_migration(engine, monkeypatch, "upgrade")

    for table in ("ai_workspace_cron", "ai_workflow_schedules", "train_schedules"):
        assert _columns(engine, table) == {"id", "trigger", "trigger_args"}, table

    assert _trigger_rows(engine, "ai_workspace_cron") == {
        1: ("cron", "0 9 * * mon"),  # 周字段 1 → mon
        2: ("cron", "0 9 * * *"),  # 6 段秒位 0 去首段 + `?`→`*`
        3: ("cron", None),  # 6 段秒位非 0 → 跳过
        4: ("cron", None),  # 7 段带年 → 跳过
        5: ("cron", "0 9 * * *"),  # 7 段年份通配 → 裁掉末段
        6: ("cron", "0 9 * * *"),  # 5 段 `?`→`*`
    }
    assert _trigger_rows(engine, "ai_workflow_schedules") == {1: ("cron", "0 9 * * *")}
    assert _trigger_rows(engine, "train_schedules") == {
        1: ("cron", "0 2 * * sun"),
        2: ("cron", None),
    }

    # 跳过的行必须逐条打印迁移日志（人工确认的依据，不能静默）
    logs = [line for line in capsys.readouterr().out.splitlines() if "[trigger 迁移]" in line]
    assert len(logs) == 3
    assert any("ai_workspace_cron#3" in line and "秒" in line for line in logs)
    assert any("ai_workspace_cron#4" in line and "年" in line for line in logs)
    assert any("train_schedules#2" in line and "无法规范化" in line for line in logs)


@requires_drop_column
def test_upgrade_is_idempotent(monkeypatch):
    """重复执行 `upgrade()` 不报错，且不改变已回填的数据。"""
    engine = _legacy_engine()
    _run_migration(engine, monkeypatch, "upgrade")
    first = _trigger_rows(engine, "ai_workspace_cron")

    _run_migration(engine, monkeypatch, "upgrade")

    assert _columns(engine, "ai_workspace_cron") == {"id", "trigger", "trigger_args"}
    assert _trigger_rows(engine, "ai_workspace_cron") == first


@requires_drop_column
def test_downgrade_rebuilds_legacy_columns_and_backfills(monkeypatch):
    """`downgrade()`：反向重建旧列并从 `trigger_args` 回填，随后删除新列。"""
    engine = _legacy_engine()
    _run_migration(engine, monkeypatch, "upgrade")
    _run_migration(engine, monkeypatch, "downgrade")

    assert _columns(engine, "ai_workspace_cron") == {"id", "cron"}
    assert _legacy_rows(engine, "ai_workspace_cron", "cron") == {
        1: "0 9 * * mon",
        2: "0 9 * * *",
        3: "",  # 迁移时跳过的行没有可回填值
        4: "",
        5: "0 9 * * *",
        6: "0 9 * * *",
    }
    assert _columns(engine, "ai_workflow_schedules") == {"id", "cron"}
    assert _legacy_rows(engine, "ai_workflow_schedules", "cron") == {1: "0 9 * * *"}
    assert _columns(engine, "train_schedules") == {"id", "cron_expr"}
    assert _legacy_rows(engine, "train_schedules", "cron_expr") == {1: "0 2 * * sun", 2: ""}


@requires_drop_column
def test_missing_plugin_tables_are_skipped(monkeypatch):
    """插件表不存在（空库全链重放）时 `has_table` 分支必须安全跳过，而非报错。"""
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE train_schedules "
                "(id INTEGER PRIMARY KEY, cron_expr VARCHAR(64) NOT NULL)"
            )
        )
        conn.execute(text("INSERT INTO train_schedules (id, cron_expr) VALUES (1, '0 2 * * 0')"))

    _run_migration(engine, monkeypatch, "upgrade")

    assert _columns(engine, "train_schedules") == {"id", "trigger", "trigger_args"}
    assert _trigger_rows(engine, "train_schedules") == {1: ("cron", "0 2 * * sun")}
    existing = set(sa.inspect(engine).get_table_names())
    assert {"ai_workspace_cron", "ai_workflow_schedules"}.isdisjoint(existing)

    # 降级同样要能容忍缺表
    _run_migration(engine, monkeypatch, "downgrade")
    assert _columns(engine, "train_schedules") == {"id", "cron_expr"}


# --------------------------------------------------------------------------- 迁移模块结构约束


def test_migration_declares_target_tables_and_parent_revision():
    """迁移覆盖三张表（旧列名/长度/可空性齐全），down_revision 指向迁移前的链尾。"""
    migration = _migration_module()

    assert migration.revision == REVISION
    assert migration.down_revision == PARENT_REVISION
    assert migration.LEGACY_COLUMNS == (
        ("ai_workspace_cron", "cron", 128, True),
        ("ai_workflow_schedules", "cron", 128, True),
        ("train_schedules", "cron_expr", 64, False),
    )


def test_migration_reuses_unified_layer_without_copying_weekday_map():
    """回填必须调用 `normalize_legacy`（统一层入口），且模块内不得复制周字段映射表。"""
    migration = _migration_module()

    backfill_source = inspect.getsource(migration._backfill_from_legacy)
    assert "normalize_legacy(" in backfill_source
    # 迁移自己不解析 cron（解析只发生在统一层，避免第二套口径）
    assert "TriggerUtil" not in backfill_source

    copied_tables = [
        name
        for name, value in vars(migration).items()
        if isinstance(value, dict) and "mon" in value
    ]
    assert copied_tables == []


def test_models_expose_trigger_columns_only():
    """三张表的模型同步为 trigger/trigger_args，旧列不再映射（不留历史包袱）。"""
    from app.plugin.module_ai.workflow.model import AiWorkflowScheduleModel
    from app.plugin.module_ai.workspace.model import AiWorkspaceCronModel
    from app.plugin.module_train.schedule_model import TrainScheduleModel

    for model, legacy_col in (
        (AiWorkspaceCronModel, "cron"),
        (AiWorkflowScheduleModel, "cron"),
        (TrainScheduleModel, "cron_expr"),
    ):
        columns = model.__table__.columns
        assert "trigger" in columns, model.__tablename__
        assert "trigger_args" in columns, model.__tablename__
        assert legacy_col not in columns, model.__tablename__
        assert columns["trigger"].nullable is False, model.__tablename__
        assert columns["trigger_args"].nullable is True, model.__tablename__
        # 接口约定：trigger VARCHAR(16) NOT NULL DEFAULT 'cron' + trigger_args TEXT NULL
        assert columns["trigger"].type.length == 16, model.__tablename__
        assert columns["trigger_args"].type.length is None, model.__tablename__
