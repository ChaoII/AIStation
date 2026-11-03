"""给燃料域的关键指标补**业务术语**（同义词），让快路径认得用户怎么说。

背景
----
指标库里其实已经有这些指标，只是**名字是"表名+列名"**：

    sum_fuel_stg_allinmiddle_qtyin  = "煤场进煤记录(流水)QTYIN合计"

用户说的是「煤场进煤总量」，两句话的 bigram 只重合"煤场进煤"（3 分 < 门槛 4），
于是一个本可 1 秒回答的问题走了 20 秒 NL2SQL。

`ai_query_dictionary`（术语）就是干这个的：命中绑定术语 +3 分，加上名字重合就过门槛。

用法::

    cd backend
    uv run python scripts/seed_fuel_terms.py            # 预览
    uv run python scripts/seed_fuel_terms.py --apply    # 写库
"""
from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import text

from app.core.database import async_db_session

DS = "ds:4"

#: (术语, 指标 key) —— 只收**语义完全一致**的说法，宁少勿多：
#: 一旦绑错，快路径会自信地答错另一个指标（这正是"指标抢答"的来源）。
TERMS: list[tuple[str, str]] = [
    ("进煤总量", "sum_fuel_stg_allinmiddle_qtyin"),
    ("进煤量合计", "sum_fuel_stg_allinmiddle_qtyin"),
    ("煤场进煤量", "sum_fuel_stg_allinmiddle_qtyin"),
    ("取煤总量", "sum_fuel_stg_alloutmiddle_qtyout"),
    ("取煤量合计", "sum_fuel_stg_alloutmiddle_qtyout"),
    ("煤场取煤量", "sum_fuel_stg_alloutmiddle_qtyout"),
    ("堆放总量", "sum_fuel_stg_deposit_totalqty"),
    ("堆煤量合计", "sum_fuel_stg_deposit_totalqty"),
    ("每日耗用量合计", "sum_fuel_report_dayinoutstorage_totaluseqty"),
    ("耗用量合计", "sum_fuel_report_dayinoutstorage_totaluseqty"),
    ("总耗用量", "sum_fuel_report_dayinoutstorage_totaluseqty"),
    ("进煤记录数", "count_fuel_stg_allinmiddle"),
    ("取煤记录数", "count_fuel_stg_alloutmiddle"),
    ("每日出入库报表记录数", "count_fuel_report_dayinoutstorage"),
]


async def main() -> None:  # pragma: no cover - 运维脚本
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    async with async_db_session() as db:
        keys = {r[0] for r in (await db.execute(text(
            "SELECT key FROM ai_query_metrics WHERE datasource=:d AND is_deleted=false"),
            {"d": DS})).fetchall()}
        existing_rows = (await db.execute(text(
            "SELECT term FROM ai_query_dictionary WHERE is_deleted=false"))).fetchall()
        existing = {r[0] for r in existing_rows}

    todo = [(t, k) for t, k in TERMS if k in keys and t not in existing]
    missing = [(t, k) for t, k in TERMS if k not in keys]
    print(f"待新增术语 {len(todo)} 条；指标不存在而跳过的 {len(missing)} 条\n")
    for t, k in todo:
        print(f"  {t:<14} → {k}")
    for t, k in missing:
        print(f"  [跳过] {t:<14} 指标不存在: {k}")

    if not args.apply:
        print("\n（预览模式；--apply 写库）")
        return
    if not todo:
        return
    async with async_db_session.begin() as db:
        for term, key in todo:
            await db.execute(text(
                "INSERT INTO ai_query_dictionary(term,metric_key,datasource,type,"
                "uuid,status,is_deleted,created_time,updated_time) "
                "VALUES (:t,:k,:d,'metric',:u,'0',false,now(),now())"),
                {"t": term, "k": key, "d": DS, "u": uuid.uuid4().hex})
    print(f"\n已新增 {len(todo)} 条术语（ds:4）")


if __name__ == "__main__":
    asyncio.run(main())
