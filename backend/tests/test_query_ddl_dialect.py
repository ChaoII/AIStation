"""问数侧「手写 SQL 的方言适配」回归测试。

背景（两次真实翻车）：
- 手写 DDL 用 PG 方言（``DEFAULT now()`` / ``BIGSERIAL``），SQLite 直接语法错，
  错误又被 best-effort 吞掉 → 表根本没建出来（``no such table: ai_access_rule``）。
- 手写 UPDATE 用 ``::text`` / ``::interval`` / ``DELETE ... r``，SQLite 不认
  → 写回动作失败、启动对账从来没生效过（且都只留一行 warning）。

这里覆盖两类断言：
1. 方言辅助函数在各种方言下拼出的片段是否合法（纯逻辑，快）；
2. 真正走到这些 SQL 的业务路径（``list_assets`` 血缘计数、``execute_action`` 写回）
   在 SQLite 上能不能跑通 —— 这两条路径**曾经都是静默失败**。
"""

import asyncio

from sqlalchemy import text as _t


def test_ddl_for_dialect_translates_pg_syntax():
    """SQLite 下 PG 方言 DDL 必须被翻译掉，否则整个 CREATE 失败。"""
    from app.plugin.module_ai.query.ddl_dialect import ddl_for_dialect

    sql = (
        "CREATE TABLE IF NOT EXISTS t (id BIGSERIAL PRIMARY KEY, "
        "j JSONB DEFAULT '[]', created_time TIMESTAMP DEFAULT now())"
    )
    out = ddl_for_dialect(sql)
    assert "BIGSERIAL" not in out
    assert "INTEGER PRIMARY KEY AUTOINCREMENT" in out
    assert "now()" not in out
    assert "CURRENT_TIMESTAMP" in out
    assert "JSONB" not in out


def test_cast_helpers_avoid_pg_only_double_colon():
    """``::text`` / ``::int`` 只有 PG 认；辅助函数必须给出各方言合法写法。"""
    from app.plugin.module_ai.query.ddl_dialect import cast_int, cast_text

    assert "::" not in cast_text('"id"')
    assert "::" not in cast_int("SUM(n)")
    assert cast_text('"id"').upper().startswith("CAST(")
    assert cast_int("SUM(n)").upper().startswith("CAST(")


def test_stale_where_has_no_interval_cast_on_sqlite():
    """启动对账的「N 分钟前」不能出现 ``::interval``（SQLite 报 unrecognized token）。"""
    from app.plugin.module_ai.query.ddl_dialect import cutoff_text, is_postgres, stale_where

    cond, param = stale_where("started_at", "m")
    if not is_postgres():
        assert "::" not in cond
        assert param == "cutoff"
        # 与 SQLite 侧 now() 的文本格式一致，才能字典序比较
        assert len(cutoff_text(30)) == len("2026-01-01 00:00:00")


def test_list_assets_lineage_count(test_client):
    """资产列表的血缘计数在 SQLite 上必须真的算出来。

    回归点：血缘那条 ``SELECT t, SUM(n)::int`` 是 PG 写法，SQLite 抛错后被
    ``except: pass`` 吞掉 → 所有资产的 ``lineage_count`` 恒为 0（界面看着正常，
    数据全是空的，最难发现的那种坏）。
    """
    from app.core.database import async_db_session
    from app.plugin.module_ai.query.model import (
        AiQueryAssetColumnModel,
        AiQueryAssetModel,
    )
    from app.plugin.module_ai.query.service import AiQueryService

    async def _go():
        try:
            async with async_db_session.begin() as db:
                await db.execute(_t(
                    "DELETE FROM ai_query_assets WHERE table_name LIKE 't_lineage_%'"))
                await db.execute(_t(
                    "DELETE FROM ai_query_asset_columns "
                    "WHERE table_name LIKE 't_lineage_%' OR related_table LIKE 't_lineage_%'"))
                db.add(AiQueryAssetModel(table_name="t_lineage_a", included=True))
                db.add(AiQueryAssetModel(table_name="t_lineage_b", included=True))
                await db.flush()
                # a.b_id 关联 b → b 被引用 1 次；a 自己有 2 个字段
                db.add(AiQueryAssetColumnModel(
                    table_name="t_lineage_a", column_name="b_id", related_table="t_lineage_b"))
                db.add(AiQueryAssetColumnModel(
                    table_name="t_lineage_a", column_name="name"))
                await db.flush()
            rows = await AiQueryService.list_assets()
            return {r["table_name"]: r for r in rows}
        finally:
            async with async_db_session.begin() as db:
                await db.execute(_t(
                    "DELETE FROM ai_query_assets WHERE table_name LIKE 't_lineage_%'"))
                await db.execute(_t(
                    "DELETE FROM ai_query_asset_columns "
                    "WHERE table_name LIKE 't_lineage_%' OR related_table LIKE 't_lineage_%'"))

    m = asyncio.run(_go())
    assert m["t_lineage_a"]["column_count"] == 2
    assert m["t_lineage_a"]["lineage_count"] == 2, "本表字段数应计入血缘"
    assert m["t_lineage_b"]["lineage_count"] == 1, "被引用次数没算出来（SQL 在 SQLite 上失败）"


def test_execute_action_writeback(test_client):
    """动作写回（P1）在 SQLite 上必须真的更新目标行。

    回归点：``WHERE "id"::text = :__k`` 只有 PG 认，SQLite 报
    ``near "::": syntax error`` → 整个动作返回「执行失败」，审计日志记 noop。
    """
    from app.core.database import async_db_session
    from app.plugin.module_ai.query.service import AiQueryService

    async def _go():
        try:
            async with async_db_session.begin() as db:
                await db.execute(_t(
                    "CREATE TABLE IF NOT EXISTS t_wb_target "
                    "(id INTEGER PRIMARY KEY, name TEXT)"))
                await db.execute(_t("DELETE FROM t_wb_target"))
                await db.execute(_t("INSERT INTO t_wb_target(id, name) VALUES (1, 'old')"))
                await db.execute(_t(
                    "DELETE FROM ai_query_writeback WHERE name='t_wb_action'"))
                await db.execute(_t(
                    "INSERT INTO ai_query_writeback("
                    "name,object_table,writable_cols,writable_by_role,validation,"
                    "approve,enabled,is_deleted) "
                    "VALUES('t_wb_action','t_wb_target','[\"name\"]','{}','',false,true,false)"))
            res = await AiQueryService.execute_action(
                "t_wb_action", "1", {"name": "new"}, "admin")
            async with async_db_session() as db:
                name = (await db.execute(_t(
                    "SELECT name FROM t_wb_target WHERE id=1"))).scalar()
            return res, name
        finally:
            async with async_db_session.begin() as db:
                await db.execute(_t("DELETE FROM ai_query_writeback WHERE name='t_wb_action'"))
                await db.execute(_t("DELETE FROM t_wb_target"))

    res, name = asyncio.run(_go())
    assert res.get("ok") is True, res
    assert res.get("rows") == 1, res
    assert name == "new"
