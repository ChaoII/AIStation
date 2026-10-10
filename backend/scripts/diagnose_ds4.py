"""ds:4（燃煤外部库）NL2SQL 差的根因排查：把各层证据一次性打出来。

用法（backend 下）::

    python scripts/diagnose_ds4.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


async def main() -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async def q(db, sql, **p):
        return (await db.execute(text(sql), p)).fetchall()

    async def section(title, fn):
        # 每节独立会话：一节报错不会 abort 掉后面所有节的 SQL
        print("=" * 78)
        print(title)
        print("=" * 78)
        try:
            async with async_db_session() as db:
                await fn(db, q)
        except Exception as e:  # noqa: BLE001
            print(f"  !! 本节失败: {type(e).__name__}: {str(e)[:200]}")
        print()

    await section("0) 相关表", lambda db, q: _tables(db, q))
    await section("0b) ai_query_* / ai_ont_* 表结构", lambda db, q: _cols(db, q))
    await section("1) 语义层：指标 / 术语 / few-shot", lambda db, q: _semantic(db, q))
    await section("2) 资产层：schema 同步 + 表/字段元数据", lambda db, q: _assets(db, q))
    await section("3) 本体层：对象 / 属性 / 关系", lambda db, q: _ontology(db, q))
    await section("4) 召回单元 / 反馈 / 沉淀", lambda db, q: _recall_feedback(db, q))
    await section("5) 评测：ds:4 逐题", lambda db, q: _eval(db, q))


async def _tables(db, q):
    rows = await q(
        db,
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' "
        "AND (table_name LIKE '%ont%' OR table_name LIKE '%eval%' OR table_name LIKE 'ai_query%' "
        "OR table_name LIKE 'ai_ont%') ORDER BY table_name",
    )
    for r in rows:
        print("  ", r[0])


async def _cols(db, q):
    rows = await q(
        db,
        "SELECT table_name, string_agg(column_name, ', ' ORDER BY ordinal_position) "
        "FROM information_schema.columns WHERE table_schema='public' "
        "AND (table_name LIKE 'ai_query%' OR table_name LIKE 'ai_ont%') "
        "GROUP BY table_name ORDER BY table_name",
    )
    for r in rows:
        print(f"  {r[0]}: {r[1]}")


async def _semantic(db, q):
    for tbl in ("ai_query_metrics", "ai_query_dictionary", "ai_query_fewshot"):
        rows = await q(
            db,
            f"SELECT datasource, COUNT(*) FROM {tbl} WHERE is_deleted=false "
            "GROUP BY datasource ORDER BY datasource",
        )
        print(f"  {tbl}: " + (", ".join(f"{r[0]}={r[1]}" for r in rows) or "(空)"))
    rows = await q(
        db,
        "SELECT key, name, enabled FROM ai_query_metrics WHERE is_deleted=false "
        "AND datasource='ds:4' ORDER BY key",
    )
    print("  ds:4 指标明细:")
    for r in rows:
        print(f"    - {r[0]} ({r[1]}) enabled={r[2]}")
    rows = await q(
        db,
        "SELECT term, COALESCE(metric_key,''), COALESCE(field_path,'') FROM ai_query_dictionary "
        "WHERE is_deleted=false AND datasource='ds:4' ORDER BY term",
    )
    print("  ds:4 术语明细:")
    for r in rows:
        print(f"    - {r[0]} → metric={r[1]} field={r[2]}")


async def _assets(db, q):
    # ai_query_schema 才是**按数据源**同步的表结构（assets 表没有 datasource 列）
    rows = await q(
        db,
        "SELECT datasource, COUNT(*), COUNT(*) FILTER (WHERE COALESCE(table_comment,'')<>'') "
        "FROM ai_query_schema WHERE is_deleted=false GROUP BY datasource ORDER BY datasource",
    )
    for r in rows:
        print(f"  ai_query_schema {r[0]}: 表={r[1]} 有表注释={r[2]}")
    rows = await q(db, "SELECT COUNT(*), COUNT(*) FILTER (WHERE included) FROM ai_query_assets "
                       "WHERE is_deleted=false")
    print(f"  ai_query_assets(全局，无 datasource 列): 总={rows[0][0]} included={rows[0][1]}")
    rows = await q(
        db,
        "SELECT COUNT(*) FILTER (WHERE COALESCE(alias,'')<>''), "
        "COUNT(*) FILTER (WHERE COALESCE(domain,'')<>''), "
        "COUNT(*) FILTER (WHERE COALESCE(description,'')<>'') FROM ai_query_assets "
        "WHERE is_deleted=false",
    )
    print(f"    其中 有中文名={rows[0][0]} 有业务域={rows[0][1]} 有描述={rows[0][2]}")
    rows = await q(
        db,
        "SELECT COUNT(*), COUNT(*) FILTER (WHERE COALESCE(description,'')<>''), "
        "COUNT(*) FILTER (WHERE COALESCE(related_table,'')<>''), "
        "COUNT(*) FILTER (WHERE COALESCE(business_scenarios,'')<>'') "
        "FROM ai_query_asset_columns WHERE is_deleted=false",
    )
    print(f"  ai_query_asset_columns: 总={rows[0][0]} 有描述={rows[0][1]} "
          f"有 related_table={rows[0][2]} 有业务场景={rows[0][3]}")
    rows = await q(
        db,
        "SELECT a.table_name, COUNT(c.column_name) FROM ai_query_assets a "
        "LEFT JOIN ai_query_asset_columns c ON c.table_name=a.table_name AND c.is_deleted=false "
        "WHERE a.is_deleted=false GROUP BY a.table_name ORDER BY 2 DESC LIMIT 5",
    )
    print("  字段元数据最多的 5 张表: " + ", ".join(f"{r[0]}={r[1]}" for r in rows))


async def _ontology(db, q):
    rows = await q(
        db,
        "SELECT datasource_id, COUNT(*) FROM ai_ont_object WHERE is_deleted=false "
        "GROUP BY datasource_id ORDER BY 1 NULLS FIRST",
    )
    print("  ai_ont_object 按 datasource_id: "
          + ", ".join(f"ds={r[0]}→{r[1]}" for r in rows))
    rows = await q(
        db,
        "SELECT o.datasource_id, COUNT(p.id) FROM ai_ont_object o "
        "LEFT JOIN ai_ont_property p ON p.object_code=o.code AND p.is_deleted=false "
        "WHERE o.is_deleted=false GROUP BY o.datasource_id ORDER BY 1 NULLS FIRST",
    )
    print("  属性数: " + ", ".join(f"ds={r[0]}→{r[1]}" for r in rows))
    rows = await q(
        db,
        "SELECT o.datasource_id, COUNT(l.id), "
        "COUNT(l.id) FILTER (WHERE l.source_field IS NOT NULL AND l.target_field IS NOT NULL) "
        "FROM ai_ont_link l JOIN ai_ont_object o ON o.code=l.source_object "
        "WHERE l.is_deleted=false GROUP BY o.datasource_id ORDER BY 1 NULLS FIRST",
    )
    print("  关系数(带字段映射): " + ", ".join(f"ds={r[0]}→{r[1]}({r[2]})" for r in rows))
    rows = await q(
        db,
        "SELECT COUNT(*) FROM ai_ont_object WHERE is_deleted=false AND datasource_id=4 "
        "AND aliases IS NOT NULL AND aliases::text NOT IN ('null', '[]', '\"\"')",
    )
    print(f"  ds:4 对象带别名(aliases): {rows[0][0]}")
    rows = await q(
        db,
        "SELECT COUNT(*) FROM ai_ont_object WHERE is_deleted=false AND datasource_id=4 "
        "AND COALESCE(description,'')<>''",
    )
    print(f"  ds:4 对象带描述: {rows[0][0]}")


async def _recall_feedback(db, q):
    rows = await q(db, "SELECT kind, COUNT(*) FROM ai_query_recall_units WHERE is_deleted=false "
                       "GROUP BY kind ORDER BY 2 DESC")
    print("  ai_query_recall_units: " + ", ".join(f"{r[0]}={r[1]}" for r in rows))
    rows = await q(db, "SELECT meta FROM ai_query_recall_units WHERE is_deleted=false LIMIT 3")
    for r in rows:
        print(f"  meta 样例: {str(r[0])[:200]}")
    rows = await q(
        db,
        "SELECT COUNT(*) FROM ai_query_recall_units WHERE is_deleted=false "
        "AND meta::text LIKE '%ds:4%'",
    )
    print(f"  其中 meta 含 ds:4 的单元: {rows[0][0]}")
    rows = await q(
        db,
        "SELECT COALESCE(NULLIF(feedback,''),'(空)'), COUNT(*), "
        "COUNT(*) FILTER (WHERE COALESCE(correct_sql,'')<>'') "
        "FROM ai_query_messages WHERE is_deleted=false GROUP BY 1 ORDER BY 2 DESC",
    )
    for r in rows:
        print(f"  feedback={r[0]}: {r[1]} 条，带 correct_sql {r[2]} 条")
    rows = await q(db, "SELECT COUNT(*) FROM ai_query_fewshot WHERE is_deleted=false")
    print(f"  few-shot 总数: {rows[0][0]}")
    rows = await q(db, "SELECT domain, COUNT(*) FROM ai_query_concept WHERE is_deleted=false "
                       "GROUP BY domain ORDER BY 1")
    print("  ai_query_concept 按 domain: " + ", ".join(f"{r[0]}={r[1]}" for r in rows))


async def _eval(db, q):
    rows = await q(
        db,
        "SELECT run_id, COUNT(*) FROM ai_query_testresult WHERE is_deleted=false "
        "AND trace->>'datasource'='ds:4' GROUP BY run_id ORDER BY run_id DESC LIMIT 3",
    )
    for r in rows:
        print(f"  run={r[0]} ds:4 题数={r[1]}")
    if not rows:
        print("  (无 ds:4 结果)")
        return
    rid = rows[0][0]
    det = await q(
        db,
        "SELECT question, is_error, path, metric_key, n_rows, gold_match, "
        "COALESCE(sql,''), trace->>'expected_metric', recall_hit, took_ms, trace, retries "
        "FROM ai_query_testresult WHERE run_id=:r AND is_deleted=false "
        "AND trace->>'datasource'='ds:4' ORDER BY id",
        r=rid,
    )
    print(f"  --- run {rid} 的 ds:4 逐题 ---")
    for r in det:
        print(f"  Q: {r[0]}")
        print(f"     error={r[1]} path={r[2]} metric={r[3]!r} rows={r[4]} match={r[5]} "
              f"expected_metric={r[7]!r} ms={r[9]} retries={r[11]}")
        print(f"     recall={r[8]}")
        print(f"     trace={r[10]}")
        print(f"     SQL: {r[6][:400]}")


asyncio.run(main())
