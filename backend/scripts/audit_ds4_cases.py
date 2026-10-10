"""量化 ds:4 测试集的有效性：逐题跑金标 SQL，看结果是"真数据"还是"空/退化"。"""

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
    ds = sys.argv[1] if len(sys.argv) > 1 else "ds:4"
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.service import _execute_custom_ds_sql, _execute_sql

    async with async_db_session() as db:
        cases = (
            await db.execute(
                text(
                    "SELECT id, question, gold_sql FROM ai_query_testcase "
                    "WHERE is_deleted=false AND datasource=:d ORDER BY id"
                ),
                {"d": ds},
            )
        ).fetchall()

    async def run(sql):
        if ds == "system":
            return await _execute_sql(sql)
        return await _execute_custom_ds_sql(int(ds.split(":")[-1]), sql)

    print(f"{ds} 测试题 {len(cases)} 道")
    buckets = {"error": [], "empty": [], "zero": [], "data": []}
    for cid, q, sql in cases:
        try:
            res = await run(sql)
            rows = res["rows"] or []
            if not rows:
                buckets["empty"].append((cid, q, "0 行"))
                continue
            flat = [v for r in rows for v in r]
            if all(v is None for v in flat):
                buckets["empty"].append((cid, q, "全 NULL"))
            elif len(flat) == 1 and flat[0] in (0, 0.0):
                buckets["zero"].append((cid, q, "单值 0"))
            else:
                buckets["data"].append((cid, q, str(rows[0])[:60]))
        except Exception as e:  # noqa: BLE001
            buckets["error"].append((cid, q, f"{type(e).__name__}: {str(e)[:80]}"))

    for k, label in (("data", "有真实数据"), ("zero", "退化(单值 0)"),
                     ("empty", "退化(空/全 NULL)"), ("error", "金标 SQL 直接报错")):
        print(f"\n=== {label}: {len(buckets[k])} 道 ===")
        for cid, q, info in buckets[k][:12]:
            print(f"  #{cid} {q[:40]} | {info}")


asyncio.run(main())
