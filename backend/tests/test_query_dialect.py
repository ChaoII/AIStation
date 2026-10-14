"""P2 多方言（G6）：`query/dialect.py` 纯逻辑测试（可 `PYTEST_NO_APP=1` 快测）。"""
from __future__ import annotations

from app.plugin.module_ai.query.dialect import (
    DIALECTS,
    build_system_prompt,
    dialect_name,
    is_templated_type,
    resolve_dialect,
    templated_note,
)


def test_resolve_postgres():
    d = resolve_dialect("postgres")
    assert d["name"] == "PostgreSQL"
    assert any("CURRENT_DATE" in r for r in d["rules"])


def test_resolve_mysql_has_curdate_no_datedetrunc():
    d = resolve_dialect("mysql")
    assert d["name"] == "MySQL"
    assert any("CURDATE()" in r for r in d["rules"])
    assert any("CONCAT" in r for r in d["rules"])
    # MySQL 绝对不能出现 date_trunc（那是 PG 专有）
    assert not any("date_trunc" in r for r in d["rules"])


def test_resolve_sqlite_has_strftime():
    d = resolve_dialect("sqlite")
    assert d["name"] == "SQLite"
    assert any("strftime" in r for r in d["rules"])
    assert not any("date_trunc" in r for r in d["rules"])
    assert not any("CURDATE()" in r for r in d["rules"])


def test_resolve_unknown_falls_back_to_postgres():
    d = resolve_dialect("oracle")
    # 未知方言必须回退 PostgreSQL，不报错
    assert d["name"] == "PostgreSQL"


def test_resolve_templated_types_fall_back():
    # file/api 是模板化数据源，无真实方言 → 回退 PG
    for t in ("file", "api"):
        assert is_templated_type(t)
        assert resolve_dialect(t)["name"] == "PostgreSQL"
        assert templated_note(t) != ""
    # 普通关系型不触发模板提示
    assert templated_note("postgres") == ""
    assert templated_note("mysql") == ""
    assert not is_templated_type("postgres")


def test_build_system_prompt_postgres_regression():
    rules = ["（1）实体列要用 name"]
    ctx = "表：video_cameras"
    prompt = build_system_prompt(resolve_dialect("postgres"), rules, ctx)
    assert "PostgreSQL 数据库查询助手" in prompt
    assert "CURRENT_DATE" in prompt
    assert "date_trunc" in prompt
    # 保留原有 GDPR/防护要求与 schema
    assert "只返回一条 SQL" in prompt
    assert ctx in prompt
    assert "实体列要用 name" in prompt


def test_build_system_prompt_mysql_no_pg_terms():
    prompt = build_system_prompt(resolve_dialect("mysql"), [], "schema")
    assert "MySQL 数据库查询助手" in prompt
    assert "date_trunc" not in prompt
    assert "CURDATE()" in prompt


def test_build_system_prompt_extra_and_templated_note():
    extra = "注意：全量不要截断。\n"
    prompt = build_system_prompt(
        resolve_dialect("postgres"), [], "ctx", extra + templated_note("api"))
    assert "全量不要截断" in prompt
    # 模板提示应被拼进来
    assert "模板化" in prompt


def test_dialect_name():
    assert dialect_name(None) == "PostgreSQL"
    assert dialect_name(resolve_dialect("mysql")) == "MySQL"


def test_dialects_cover_three_kinds():
    assert {"postgres", "mysql", "sqlite"} <= set(DIALECTS)
