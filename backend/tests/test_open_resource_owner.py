# tests/test_open_resource_owner.py
"""P2 归属列迁移：真实 SQLite 升降级往返 + 结构守卫 + 模型列断言。"""
from importlib import import_module
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MOD = import_module("app.alembic.versions.2026_10_22_ai_open_resource_owner")
REVISION = "b7c8d9e0f1a2"
DOWN_REVISION = "a9b8c7d6e5f4"

AGENTS = "ai_agents"
TASKS = "train_tasks"


def _engine(create_agents: bool = True) -> sa.Engine:
    """最小化前置表：集成应用 + 两张目标表。"""
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE ai_integration_apps (id INTEGER PRIMARY KEY)"))
        if create_agents:
            conn.execute(sa.text("CREATE TABLE ai_agents (id INTEGER PRIMARY KEY)"))
        conn.execute(sa.text("CREATE TABLE train_tasks (id INTEGER PRIMARY KEY)"))
    return engine


def _run(migration_fn, engine: sa.Engine) -> None:
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migration_fn()


def _columns(engine: sa.Engine, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


def test_upgrade_downgrade_roundtrip():
    engine = _engine()

    _run(MOD.upgrade, engine)
    assert "source_app_id" in _columns(engine, AGENTS)
    assert "source_app_id" in _columns(engine, TASKS)
    assert {i["name"] for i in sa.inspect(engine).get_indexes(TASKS)} >= {
        f"ix_{TASKS}_source_app_id"
    }

    _run(MOD.downgrade, engine)
    assert "source_app_id" not in _columns(engine, AGENTS)
    assert "source_app_id" not in _columns(engine, TASKS)

    # 幂等：重复 upgrade 不炸
    _run(MOD.upgrade, engine)
    assert "source_app_id" in _columns(engine, TASKS)


def test_upgrade_skips_missing_plugin_table():
    """空库全链重放：插件表（ai_agents）尚不存在时跳过，不抛异常。"""
    engine = _engine(create_agents=False)
    _run(MOD.upgrade, engine)
    assert "source_app_id" in _columns(engine, TASKS)
    assert AGENTS not in sa.inspect(engine).get_table_names()


def test_migration_declares_expected_revision_chain():
    assert MOD.revision == REVISION
    assert MOD.down_revision == DOWN_REVISION


def test_migration_is_guarded():
    src = (
        Path(__file__).parent.parent
        / "app"
        / "alembic"
        / "versions"
        / "2026_10_22_ai_open_resource_owner.py"
    ).read_text(encoding="utf-8")
    assert "get_table_names" in src and "get_columns" in src
    assert '"source_app_id" in _columns' in src


def test_models_declare_source_app_id():
    """模型层必须同步声明归属列（否则 create_all 出来的库缺列）。"""
    from app.plugin.module_ai.agent.model import AiAgentModel
    from app.plugin.module_train.model import TrainTask

    assert "source_app_id" in AiAgentModel.__table__.columns
    assert "source_app_id" in TrainTask.__table__.columns
