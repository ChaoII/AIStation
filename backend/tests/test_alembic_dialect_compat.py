"""Alembic 跨方言兼容层回归（PG / SQLite / MySQL）。

锁住两点：
1. ``postgresql.JSONB`` 在 SQLite/MySQL 上降级渲染为 ``JSON``（PG 仍为 JSONB）；
2. ``alembic upgrade head`` 可在**临时 SQLite 文件**上从空库一跑到底（真实子进程）。
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CreateTable

import app.alembic.dialect_compat  # noqa: F401  触发 @compiles 注册

BACKEND_DIR = Path(__file__).parent.parent


def _render(dialect_module) -> str:
    table = sa.Table("t_jsonb", sa.MetaData(), sa.Column("data", JSONB))
    return str(CreateTable(table).compile(dialect=dialect_module.dialect()))


def test_jsonb_renders_as_json_on_sqlite():
    assert "JSON" in _render(sqlite) and "JSONB" not in _render(sqlite)


def test_jsonb_renders_as_json_on_mysql():
    out = _render(mysql)
    assert "JSON" in out and "JSONB" not in out


def test_jsonb_kept_on_postgres():
    assert "JSONB" in _render(postgresql)


def test_sqlite_upgrade_head_from_empty(tmp_path):
    """实证：SQLite 空库 `alembic upgrade head` 可完整重放并落到 head。"""
    db_stem = (tmp_path / "mig_replay").as_posix()
    db_file = Path(f"{db_stem}.db")
    env = os.environ.copy()
    env.update(
        {
            "ENVIRONMENT": "dev",
            "DATABASE_TYPE": "sqlite",
            "DATABASE_NAME": db_stem,
        }
    )
    env.pop("TESTING", None)
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, (proc.stdout[-2000:] + "\n" + proc.stderr[-4000:])
    assert db_file.exists()

    con = sqlite3.connect(db_file)
    version = con.execute("select version_num from alembic_version").fetchone()[0]
    assert version == _head_revision()
    tables = {
        r[0]
        for r in con.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
        )
    }
    assert {"video_cameras", "video_alarm_rules", "ai_models", "train_predicts"} <= tables
    # 关键结构：作用域 CHECK、分组外键、JSONB→JSON（sqlite_master 中不出现 JSONB）
    rule_ddl = con.execute(
        "select sql from sqlite_master where name='video_alarm_rules'"
    ).fetchone()[0]
    assert "ck_video_alarm_rules_scope_xor" in rule_ddl
    assert "JSONB" not in rule_ddl
    con.close()


def _run_alembic(db_stem: str, *args: str) -> subprocess.CompletedProcess:
    """在指定临时 SQLite 库上跑 alembic（真实子进程）。"""
    env = os.environ.copy()
    env.update(
        {
            "ENVIRONMENT": "dev",
            "DATABASE_TYPE": "sqlite",
            "DATABASE_NAME": db_stem,
        }
    )
    env.pop("TESTING", None)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def test_sqlite_upgrade_tolerates_missing_legacy_created_at(tmp_path):
    """复现 dev 库漂移：video_layouts 无遗留 created_at 时补列迁移不得崩溃。

    场景：表由模型 create_all 建立（有 created_time、无 created_at），
    alembic 版本停在 ``b2c3d4e5f6a7``，随后 upgrade head 需跑
    ``a3f3956bb77b`` 的 ``UPDATE ... COALESCE(created_time, created_at, NOW())``。
    """
    db_stem = (tmp_path / "drift_replay").as_posix()
    db_file = Path(f"{db_stem}.db")

    p1 = _run_alembic(db_stem, "upgrade", "b2c3d4e5f6a7")
    assert p1.returncode == 0, p1.stdout[-2000:] + "\n" + p1.stderr[-3000:]

    con = sqlite3.connect(db_file)
    con.execute("ALTER TABLE video_layouts DROP COLUMN created_at")
    con.execute("ALTER TABLE video_layouts DROP COLUMN updated_at")
    con.commit()
    con.close()

    p2 = _run_alembic(db_stem, "upgrade", "head")
    assert p2.returncode == 0, p2.stdout[-2000:] + "\n" + p2.stderr[-4000:]

    con = sqlite3.connect(db_file)
    version = con.execute("select version_num from alembic_version").fetchone()[0]
    con.close()
    assert version == _head_revision()


def _head_revision() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from app.config.path_conf import ALEMBIC_VERSION_DIR

    cfg = Config()
    cfg.set_main_option("script_location", str(ALEMBIC_VERSION_DIR.parent))
    return ScriptDirectory.from_config(cfg).get_current_head()
