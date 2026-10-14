"""窗口函数失败题：直接执行金标与模型 SQL，看比对到底卡在哪。"""

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
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query import executor as _ex
    from app.plugin.module_ai.query.benchmark import lenient_match
    from app.plugin.module_ai.query.service import (
        _ds_cfg_from_model, _execute_custom_ds_sql, _load_ds,
    )

    ds = await _load_ds(4)
    cfg = _ds_cfg_from_model(ds)

    async with async_db_session() as db:
        rid = (
            await db.execute(
                text(
                    "SELECT run_id FROM ai_query_testresult WHERE is_deleted=false "
                    "AND trace->>'datasource'='ds:4' GROUP BY run_id ORDER BY MAX(id) DESC LIMIT 1"
                )
            )
        ).scalar()
        rows = (
            await db.execute(
                text(
                    "SELECT r.question, COALESCE(r.sql,'') FROM ai_query_testresult r "
                    "WHERE r.run_id=:rid AND r.is_deleted=false AND r.trace->>'form'='窗口函数' "
                    "AND r.gold_match=false ORDER BY r.id LIMIT 6"
                ),
                {"rid": rid},
            )
        ).fetchall()
        gold = {
            str(r[0]): str(r[1])
            for r in (
                await db.execute(
                    text(
                        "SELECT question, gold_sql FROM ai_query_testcase "
                        "WHERE is_deleted=false AND datasource='ds:4'"
                    )
                )
            ).fetchall()
        }

    for q, msql in rows:
        gsql = gold.get(q) or ""
        print("=" * 74)
        print(f"Q: {q[:46]}")
        try:
            g = await _execute_custom_ds_sql(4, gsql)
        except Exception as e:  # noqa: BLE001
            print(f"  金标执行失败: {str(e)[:90]}")
            continue
        try:
            m = await _execute_custom_ds_sql(4, msql)
        except Exception as e:  # noqa: BLE001
            print(f"  模型执行失败: {str(e)[:90]}")
            continue
        same = len(g["rows"]) == len(m["rows"])
        ok = lenient_match(g["columns"], g["rows"], m["columns"], m["rows"])
        print(f"  行数: 金标={len(g['rows'])} 模型={len(m['rows'])}  {'相同' if same else '**不同**'}")
        print(f"  列: 金标={g['columns']}")
        print(f"      模型={m['columns']}")
        print(f"  lenient_match={ok}")
        if g["rows"]:
            print(f"  金标首行={g['rows'][0]}")
        if m["rows"]:
            print(f"  模型首行={m['rows'][0]}")


asyncio.run(main())
