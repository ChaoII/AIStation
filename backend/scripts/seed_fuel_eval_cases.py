"""把 ds:4 评测题库整理成「能真出数」的可用集合。

现状（实测）：254 道题**全部 enabled=false**，且不少金标 SQL 指向空表
（如 `FUEL_CB_COALBALANCE` 0 行），跑评测等于空转。

做法：逐题真跑 `gold_sql`——
- 有行 → `verified=true, enabled=true`（可评测，也能当问数正样本）；
- 无行/报错 → `verified=false, enabled=false`（保留但不参与评测）。

用法::

    cd backend
    uv run python scripts/fix_fuel_eval_cases.py [--max-enable 30]
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from app.core.database import async_db_session
from app.plugin.module_ai.query import executor as _ex

DS_CODE = "ds:4"


async def main() -> None:  # pragma: no cover - 运维脚本
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-enable", type=int, default=30)
    args = ap.parse_args()

    async with async_db_session() as db:
        ds = (await db.execute(text(
            "SELECT type,host,port,database,username,password "
            "FROM ai_query_datasources WHERE id=4"))).fetchone()
        cases = (await db.execute(text(
            "SELECT id,question,gold_sql,enabled,verified FROM ai_query_testcase "
            "WHERE is_deleted=false AND datasource=:d ORDER BY id"), {"d": DS_CODE})).fetchall()
    cfg = {"type": ds[0], "host": ds[1], "port": ds[2], "database": ds[3],
           "username": ds[4], "password": ds[5]}

    good: list[tuple[int, str]] = []
    bad = 0
    for cid, question, gold, _enabled, _verified in cases:
        sql = str(gold or "").strip().rstrip(";")
        if not sql:
            bad += 1
            continue
        try:
            out = await _ex.execute_select(cfg, sql)
            rows = out.get("rows") or []
        except Exception:  # noqa: BLE001
            bad += 1
            continue
        if rows and not all(all(v is None for v in r) for r in rows):
            good.append((cid, question))
        else:
            bad += 1

    print(f"金标可出数 {len(good)} 题 / 空或报错 {bad} 题（共 {len(cases)}）")
    enable_ids = [cid for cid, _ in good[: args.max_enable]]
    async with async_db_session.begin() as db:
        await db.execute(text(
            "UPDATE ai_query_testcase SET enabled=false WHERE is_deleted=false AND datasource=:d"),
            {"d": DS_CODE})
        await db.execute(text(
            "UPDATE ai_query_testcase SET enabled=true, verified=true "
            "WHERE is_deleted=false AND id = ANY(:ids)"), {"ids": enable_ids})
        await db.execute(text(
            "UPDATE ai_query_testcase SET verified=false "
            "WHERE is_deleted=false AND datasource=:d AND NOT (id = ANY(:ids))"),
            {"d": DS_CODE, "ids": enable_ids})
    print(f"已启用 {len(enable_ids)} 题：")
    for cid, q in good[: args.max_enable]:
        print("  -", cid, q)


asyncio.run(main())
