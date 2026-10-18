"""触发列统一迁移（A6）：迁移助手逻辑 + 手写迁移静态约束。

测试库为 SQLite，Alembic 的建表/删列 DDL 在 SQLite 上未必可重放（既有机制会跳过），
因此断言以 ``app.utils.trigger_migration`` 的助手与迁移源码的静态约束为主；
回填/降级两条链路用**内存 SQLite** 直接驱动迁移模块的助手函数验证（不依赖 Alembic 运行时）。
"""

from importlib import import_module
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, text

VERSIONS_DIR = Path(__file__).parent.parent / "app" / "alembic" / "versions"

#: 本次迁移的 revision（与 `2026_10_18_unify_trigger_columns.py` 一致）
REVISION = "f6b7c8d9e0a1"
#: 迁移链尾（A6 之前的 head），down_revision 必须指向它
PARENT_REVISION = "e2f3a4b5c6d7"


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


def _legacy_table_engine() -> sa.Engine:
    """内存 SQLite：模拟「已 add_column 但尚未回填/删旧列」的三表之一。"""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE ai_workspace_cron ("
                "id INTEGER PRIMARY KEY, cron VARCHAR(128), "
                "trigger VARCHAR(16) NOT NULL DEFAULT 'cron', trigger_args TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO ai_workspace_cron (id, cron) VALUES "
                "(1, '0 9 * * 1'), (2, '30 * * * * *'), (3, '0 0 9 * * * 2030'), (4, '0 0 9 * * *')"
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


def test_normalize_legacy_skips_empty_and_invalid():
    """空值/无法规范化的旧值 → 跳过并给出中文原因（trigger_args 留空待人工确认）。"""
    from app.utils.trigger_migration import normalize_legacy

    for value in (None, "", "   "):
        trigger, args, skip = normalize_legacy(value)
        assert (trigger, args) == ("cron", None)
        assert skip and "空" in skip

    trigger, args, skip = normalize_legacy("0 9 32 * *")
    assert (trigger, args) == ("cron", None)
    assert skip and "无法规范化" in skip


def test_backfill_from_legacy_writes_normalized_and_keeps_skips_null():
    """回填助手：可等值转换的写回规范化值，跳过的行保持 NULL 并逐条记录日志。"""
    migration = _migration_module()
    engine = _legacy_table_engine()
    with engine.begin() as conn:
        logs = migration._backfill_from_legacy(conn, "ai_workspace_cron", "cron")
        rows = {
            row.id: (row.trigger, row.trigger_args)
            for row in conn.execute(text("SELECT id, trigger, trigger_args FROM ai_workspace_cron"))
        }

    assert rows[1] == ("cron", "0 9 * * mon")
    assert rows[4] == ("cron", "0 9 * * *")
    # 跳过的两行：trigger 保持默认值、trigger_args 留空（由列表接口标为"需人工确认"）
    assert rows[2] == ("cron", None)
    assert rows[3] == ("cron", None)
    assert len(logs) == 2
    assert "秒" in logs[0] and "年" in logs[1]


def test_restore_legacy_from_args_backfills_old_column():
    """降级助手：从 trigger_args 反向重建旧列，非 cron 的行写空串（旧列非空约束）。"""
    migration = _migration_module()
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE train_schedules ("
                "id INTEGER PRIMARY KEY, cron_expr VARCHAR(64), "
                "trigger VARCHAR(16) NOT NULL DEFAULT 'cron', trigger_args TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO train_schedules (id, trigger, trigger_args) VALUES "
                "(1, 'cron', '0 2 * * sun'), (2, 'interval', '{\"hours\": 2}'), (3, 'cron', NULL)"
            )
        )
        restored = migration._restore_legacy_from_args(conn, "train_schedules", "cron_expr")
        rows = {
            row.id: row.cron_expr
            for row in conn.execute(text("SELECT id, cron_expr FROM train_schedules"))
        }

    assert restored == 3
    assert rows[1] == "0 2 * * sun"
    assert rows[2] == ""  # 非 cron 的旧列无对应值
    assert rows[3] == ""


# --------------------------------------------------------------------------- 迁移源码静态约束


def test_migration_targets_three_tables_and_parent_revision():
    """迁移覆盖三张表、down_revision 指向当前链尾，且旧列类型按表还原。"""
    migration = _migration_module()

    assert migration.revision == REVISION
    assert migration.down_revision == PARENT_REVISION
    tables = {table for table, _legacy, _length, _nullable in migration.LEGACY_COLUMNS}
    assert tables == {"ai_workspace_cron", "ai_workflow_schedules", "train_schedules"}
    legacy_cols = {legacy for _table, legacy, _length, _nullable in migration.LEGACY_COLUMNS}
    assert legacy_cols == {"cron", "cron_expr"}


def test_migration_is_guarded_and_reuses_trigger_util():
    """插件表先做 has_table 判定（空库重放兼容）；规范化复用 TriggerUtil，不复制映射表。"""
    source = _migration_path().read_text(encoding="utf-8")
    assert "has_table" in source
    assert "op.drop_column" in source
    assert "from app.utils.trigger_migration import normalize_legacy" in source
    # 不得在本迁移里复制周字段映射表（口径唯一，一律复用 TriggerUtil）
    assert "_WEEKDAY_MAP" not in source
    assert '"sun": "sun"' not in source


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
