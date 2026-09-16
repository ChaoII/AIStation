"""迁移链可从空库重放 + 补齐迁移缺失表/列的回归测试（静态校验）。

真正「空库 upgrade head → 模型 schema 比对为空」的证明在临时库上手工完成；
这里用静态断言锁住关键约束，避免回归：
1. 三条历史迁移不得再对 base 从未创建的 ``apscheduler_jobs`` 做无条件 drop；
2. 补齐迁移必须声明全部 17 张缺失表，且使用幂等 DDL（IF NOT EXISTS）；
3. 新增列迁移必须做存在性/幂等保护。
"""
from importlib import import_module
from pathlib import Path

VERSIONS_DIR = Path(__file__).parent.parent / "app" / "alembic" / "versions"

# 迁移路径历史上缺失、由 a3f3956bb77b 补齐的表
MISSING_TABLES = {
    "ai_apps", "ai_call_logs", "ai_messages", "ai_models", "ai_prompts",
    "ai_providers", "ai_reports", "ai_sessions", "ai_tools",
    "annotation_dataset", "annotation_image", "annotation_record", "annotation_task",
    "sys_user_notification", "train_predicts", "video_edge_devices",
    "video_record_execution_logs",
}

APSCHEDULER_MIGRATIONS = ("a923822e9bef", "2e9f6ccd3ff4", "38d18b9077de")


def _read(revision: str) -> str:
    matches = list(VERSIONS_DIR.glob(f"{revision}_*.py"))
    assert len(matches) == 1, f"期望唯一迁移文件: {revision} -> {matches}"
    return matches[0].read_text(encoding="utf-8")


def test_apscheduler_drop_is_guarded():
    """BLOCKER-1：空库重放时 apscheduler_jobs 不存在，不得无条件 drop。"""
    for rev in APSCHEDULER_MIGRATIONS:
        src = _read(rev)
        assert "def _drop_apscheduler_jobs" in src, rev
        assert "has_table" in src, rev
        # drop_table 只允许出现在带 has_table 保护的 helper 内
        assert src.count("op.drop_table('apscheduler_jobs')") + src.count(
            'op.drop_table("apscheduler_jobs")'
        ) == 1, rev


def test_reconcile_migration_declares_all_missing_tables():
    """H6：补齐迁移必须覆盖全部缺失表。"""
    mod = import_module("app.alembic.versions.a3f3956bb77b_补齐迁移缺失表与列")
    ddl = "\n".join(mod._TABLE_DDL)
    for table in MISSING_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table} " in ddl, table


def test_reconcile_migration_is_idempotent():
    """BLOCKER-3：建表/补列/索引一律使用幂等 DDL，兼容先兜底后迁移。"""
    mod = import_module("app.alembic.versions.a3f3956bb77b_补齐迁移缺失表与列")
    assert mod.down_revision == "b2c3d4e5f6a7"
    for stmt in mod._COLUMN_DDL:
        assert "IF NOT EXISTS" in stmt, stmt
    for col in ("conditions", "scene_type", "reachable", "edge_device_id", "error_log"):
        assert f" {col} " in "\n".join(mod._COLUMN_DDL), col


def test_guarded_add_column_migrations():
    """BLOCKER-3：兜底已补的参数列，迁移侧必须做存在性探测。"""
    for rev in ("1164d4a7539d", "183fb76b1184", "b2c3d4e5f6a7", "38d18b9077de", "d6d5f85952f5"):
        src = _read(rev)
        guarded = (
            "_has_column" in src
            or "_column_names" in src
            or "_has_index" in src
            or "IF NOT EXISTS" in src
        )
        assert guarded, rev
