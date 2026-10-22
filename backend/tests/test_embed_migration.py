# tests/test_embed_migration.py
"""P4' 迁移：真实 SQLite 升降级往返 + 结构守卫静态断言。"""
from importlib import import_module
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MOD = import_module("app.alembic.versions.2026_10_21_ai_integration_embed")
REVISION = "a9b8c7d6e5f4"
DOWN_REVISION = "c9d0e1f2a3b4"

TOKEN_TABLE = "ai_integration_access_tokens"
EMBED_SESSION_TABLE = "ai_integration_embed_sessions"


def _engine() -> sa.Engine:
    """最小化前置表：只建迁移会触碰的三张既有表。"""
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE ai_integration_apps (id INTEGER PRIMARY KEY)"))
        conn.execute(
            sa.text("CREATE TABLE ai_assistant_sessions (id INTEGER PRIMARY KEY, title VARCHAR(255))")
        )
        conn.execute(
            sa.text("CREATE TABLE ai_workflows (id INTEGER PRIMARY KEY, share_token VARCHAR(64))")
        )
    return engine


def _run(migration_fn, engine: sa.Engine) -> None:
    """在给定引擎上执行迁移函数（模拟 alembic op 上下文）。"""
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migration_fn()


def _columns(engine: sa.Engine, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


def test_upgrade_downgrade_roundtrip():
    engine = _engine()

    # upgrade：两表建好、会话归属列就位、旧分享列移除
    _run(MOD.upgrade, engine)
    tables = set(sa.inspect(engine).get_table_names())
    assert {TOKEN_TABLE, EMBED_SESSION_TABLE}.issubset(tables)
    assert "source_app_id" in _columns(engine, "ai_assistant_sessions")
    assert "share_token" not in _columns(engine, "ai_workflows")
    # token_hash 唯一索引（库内只存散列）
    token_indexes = {i["name"]: i for i in sa.inspect(engine).get_indexes(TOKEN_TABLE)}
    assert token_indexes[f"ix_{TOKEN_TABLE}_token_hash"]["unique"] in (True, 1)

    # downgrade：恢复分享列、移除归属列、两表消失
    _run(MOD.downgrade, engine)
    tables = set(sa.inspect(engine).get_table_names())
    assert TOKEN_TABLE not in tables and EMBED_SESSION_TABLE not in tables
    assert "source_app_id" not in _columns(engine, "ai_assistant_sessions")
    assert "share_token" in _columns(engine, "ai_workflows")

    # 再 upgrade 一次：证明幂等（重复执行不炸）
    _run(MOD.upgrade, engine)
    tables = set(sa.inspect(engine).get_table_names())
    assert {TOKEN_TABLE, EMBED_SESSION_TABLE}.issubset(tables)


def test_migration_declares_expected_revision_chain():
    assert MOD.revision == REVISION
    assert MOD.down_revision == DOWN_REVISION


def test_migration_is_guarded():
    """空库全链重放安全：建表/改列全部做存在性探测，不得出现无条件 DDL。"""
    src = (
        Path(__file__).parent.parent
        / "app"
        / "alembic"
        / "versions"
        / "2026_10_21_ai_integration_embed.py"
    ).read_text(encoding="utf-8")
    assert "get_table_names" in src and "get_columns" in src
    # 删列必须落在 has_column 守卫分支内（_columns/ `"share_token" in` 探测）
    assert '"share_token" in _columns' in src
