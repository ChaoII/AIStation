"""看弱项形式到底错在哪：模型 SQL vs 金标 SQL 逐题对照。"""

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


async def main(form: str) -> None:
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session() as db:
        rid = (
            await db.execute(
                text(
                    "SELECT run_id FROM ai_query_testresult WHERE is_deleted=false "
                    "AND trace->>'datasource'='ds:4' GROUP BY run_id "
                    "ORDER BY MAX(id) DESC LIMIT 1"
                )
            )
        ).scalar()
        print(f"最近一轮 run={rid}")
        rows = (
            await db.execute(
                text(
                    "SELECT r.question, r.is_error, r.n_rows, r.gold_match, "
                    "COALESCE(r.sql,''), r.trace->>'difficulty' "
                    "FROM ai_query_testresult r WHERE r.run_id=:rid AND r.is_deleted=false "
                    "AND r.trace->>'form'=:f ORDER BY r.id"
                ),
                {"rid": rid, "f": form},
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
    print(f"form={form} 共 {len(rows)} 题")
    for q, err, n, match, sql, diff in rows:
        print("=" * 78)
        print(f"Q: {q}   [{'✓' if match else '✗'}] error={err} rows={n} 难度={diff}")
        print(f"  模型: {sql[:300] or '(空)'}")
        print(f"  金标: {(gold.get(q) or '(缺)')[:300]}")


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "窗口函数"))
