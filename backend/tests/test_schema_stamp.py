"""启动期 Alembic 版本戳检测/补写回归（审计 I1：create_all 建的库无 alembic_version）。

语义：
- 空库（无业务表）→ 不写戳（交给 create_all / 迁移）；
- 已有 alembic_version 记录 → 不动；
- 表存在但无记录且 schema 与当前模型一致（create_all 建库）→ 补写 head；
- 表存在但无记录且缺列（旧 schema）→ **拒绝**，给出明确操作指引。
"""
import sqlalchemy as sa
from sqlalchemy import create_engine, text

from app.scripts.schema_stamp import (
    StampState,
    apply_stamp,
    evaluate,
    get_head_revision,
    get_model_schema,
)

EXPECTED = {"t_demo": {"id", "name"}, "t_other": {"id"}}


def _conn():
    engine = create_engine("sqlite://")
    return engine.connect()


def _make(conn, ddl: str) -> None:
    conn.execute(text(ddl))


def test_evaluate_no_tables():
    conn = _conn()
    d = evaluate(conn, expected=EXPECTED)
    assert d.state is StampState.NO_TABLES


def test_evaluate_already_stamped():
    conn = _conn()
    _make(
        conn,
        "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)",
    )
    conn.execute(text("INSERT INTO alembic_version VALUES ('abc123')"))
    d = evaluate(conn, expected=EXPECTED)
    assert d.state is StampState.ALREADY_STAMPED
    assert d.revision == "abc123"


def test_evaluate_schema_matches():
    conn = _conn()
    _make(conn, "CREATE TABLE t_demo (id INTEGER, name TEXT)")
    _make(conn, "CREATE TABLE t_other (id INTEGER)")
    d = evaluate(conn, expected=EXPECTED)
    assert d.state is StampState.SCHEMA_MATCHES_HEAD
    assert d.missing == []


def test_evaluate_legacy_missing_column():
    conn = _conn()
    _make(conn, "CREATE TABLE t_demo (id INTEGER)")  # 缺 name
    _make(conn, "CREATE TABLE t_other (id INTEGER)")
    d = evaluate(conn, expected=EXPECTED)
    assert d.state is StampState.LEGACY_MISMATCH
    assert any("t_demo" in m for m in d.missing)


def test_apply_stamp_writes_head():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        _make(conn, "CREATE TABLE t_demo (id INTEGER, name TEXT)")
        _make(conn, "CREATE TABLE t_other (id INTEGER)")
    d = apply_stamp(engine, expected=EXPECTED, head="deadbeef")
    assert d.state is StampState.SCHEMA_MATCHES_HEAD
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
    assert row[0] == "deadbeef"


def test_apply_stamp_refuses_legacy():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        _make(conn, "CREATE TABLE t_demo (id INTEGER)")  # 缺 name
        _make(conn, "CREATE TABLE t_other (id INTEGER)")
    d = apply_stamp(engine, expected=EXPECTED, head="deadbeef")
    assert d.state is StampState.LEGACY_MISMATCH
    with engine.connect() as conn:
        assert not sa.inspect(conn).has_table("alembic_version")


def test_get_head_revision_matches_script_directory():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from app.config.path_conf import ALEMBIC_VERSION_DIR

    cfg = Config()
    cfg.set_main_option("script_location", str(ALEMBIC_VERSION_DIR.parent))
    assert get_head_revision() == ScriptDirectory.from_config(cfg).get_current_head()


def test_get_model_schema_covers_current_models():
    schema = get_model_schema()
    assert "video_cameras" in schema
    assert {"id", "uuid", "reachable", "group_id"} <= schema["video_cameras"]
    assert {"parent_id", "name"} <= schema["video_camera_groups"]
