"""为燃煤业务库（ds:4）造一套**能真出数**的问数评测题（dataset=fuel-demo）。

背景：库里 254 道 ds:4 题大多是「表格自动生成」的，大量建在空表上
（`FUEL_CB_COALBALANCE` 等 0 行）→ 金标本身就是 NULL，评测等于空转。
这里手写一套基于**有真实数据**的表/列的问题（化验单 2527 行、入厂批次 277、
矿点 65、煤种 19、煤质 77、供应商矿点关系 140、区域 400），并先跑金标校验。

用法::

    cd backend
    uv run python scripts/seed_fuel_ask_cases.py
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.core.database import async_db_session
from app.plugin.module_ai.query import executor as _ex

DS_CODE = "ds:4"
DATASET = "fuel-demo"

#: (问题, 金标 SQL, 难度, 场景, 形态, 期望指标 key)
CASES: list[tuple[str, str, str, str, str, str]] = [
    ("入厂煤化验单一共有多少条？",
     'SELECT COUNT(*) AS "化验单数" FROM "FUEL_CMCS_ASSAY"', "简单", "化验管理", "单维统计", "coal_assay_count"),
    ("入厂煤批次一共有多少条？",
     'SELECT COUNT(*) AS "入厂批次数" FROM "FUEL_CMCS_INFACTORYBATCH"', "简单", "入厂批次", "单维统计", "coal_batch_count"),
    ("矿点一共有多少个？",
     'SELECT COUNT(*) AS "矿点数" FROM "FUEL_CMCS_MINE"', "简单", "基础档案", "单维统计", "coal_mine_count"),
    ("煤种一共有多少种？",
     'SELECT COUNT(*) AS "煤种数" FROM "FUEL_CMCS_FUELKIND"', "简单", "基础档案", "单维统计", "coal_fuelkind_count"),
    ("各煤种的平均干基全硫是多少？",
     'SELECT "COALTYPE" AS "煤种", ROUND(AVG(CAST("LF" AS numeric))::numeric, 2) AS "平均干基全硫" '
     'FROM "DTXY_PMXX" WHERE "LF" IS NOT NULL GROUP BY "COALTYPE" ORDER BY "平均干基全硫" DESC',
     "中等", "煤质分析", "分组聚合", "avg_lf"),
    ("各煤种的平均收到基低位发热量是多少？",
     'SELECT "COALTYPE" AS "煤种", ROUND(AVG(CAST("RZ" AS numeric))::numeric, 2) AS "平均收到基低位发热量" '
     'FROM "DTXY_PMXX" WHERE "RZ" IS NOT NULL GROUP BY "COALTYPE" ORDER BY "平均收到基低位发热量" DESC',
     "中等", "煤质分析", "分组聚合", "avg_rz"),
    ("入厂煤的验收量合计是多少？",
     'SELECT SUM("CHECKQTY") AS "结算总量" FROM "FUEL_CMCS_INFACTORYBATCH"',
     "中等", "结算", "单维聚合", "total_settlement_qty"),
    ("平均合同单价是多少？",
     'SELECT ROUND(AVG(CAST("CONTRACTPRICE" AS numeric))::numeric, 2) AS "平均合同单价" '
     'FROM "VIEW_GETBATCHPRICE" WHERE "CONTRACTPRICE" IS NOT NULL',
     "中等", "结算", "单维聚合", "avg_contract_price"),
    ("供应商矿点关系一共有多少条？",
     'SELECT COUNT(*) AS "供应商矿点关系数" FROM "DTXY_GYSKDGX"', "简单", "基础档案", "单维统计",
     "DTXY_GYSKDGX_count_ID"),
    ("区域一共有多少个？",
     'SELECT COUNT(*) AS "区域数量" FROM "DTXY_QYXX"', "简单", "基础档案", "单维统计",
     "DTXY_QYXX_count_ID"),
    ("按矿点统计入厂煤批次数量",
     'SELECT COALESCE("MINENAME", \'\') AS "矿点", COUNT(*) AS "批次数" '
     'FROM "FUEL_CMCS_INFACTORYBATCH" GROUP BY 1 ORDER BY "批次数" DESC',
     "较难", "入厂批次", "分组聚合", ""),
    ("运损合计是多少？",
     'SELECT SUM(CAST("RAILLOST" AS numeric)) AS "运损合计" FROM "FUEL_CMCS_INFACTORYBATCH"',
     "中等", "入厂批次", "单维聚合", "fuel_raillost_total"),
]


async def _cfg() -> dict:
    async with async_db_session() as db:
        r = (await db.execute(text(
            "SELECT type,host,port,database,username,password "
            "FROM ai_query_datasources WHERE id=4"))).fetchone()
    return {"type": r[0], "host": r[1], "port": r[2], "database": r[3],
            "username": r[4], "password": r[5]}


async def main() -> None:  # pragma: no cover - 运维脚本
    cfg = await _cfg()
    ok, skipped = 0, []
    for q, sql, diff, scen, form, metric in CASES:
        try:
            out = await _ex.execute_select(cfg, sql)
        except Exception as e:  # noqa: BLE001
            skipped.append((q, str(e)[:80]))
            continue
        rows = out.get("rows") or []
        flat = [v for r in rows for v in (r if isinstance(r, (list, tuple)) else [r])]
        if not rows or all(v is None for v in flat):
            skipped.append((q, "空结果"))
            continue
        async with async_db_session.begin() as db:
            exists = (await db.execute(text(
                "SELECT id FROM ai_query_testcase WHERE datasource=:d AND question=:q "
                "AND is_deleted=false"), {"d": DS_CODE, "q": q})).scalar()
            if exists:
                await db.execute(text(
                    "UPDATE ai_query_testcase SET gold_sql=:s, difficulty=:df, scenario=:sc, "
                    "form=:f, expected_metric=:em, dataset=:ds, verified=true, enabled=true, "
                    "last_verified_at=now(), updated_time=now() WHERE id=:i"),
                    {"s": sql, "df": diff, "sc": scen, "f": form, "em": metric,
                     "ds": DATASET, "i": exists})
            else:
                await db.execute(text(
                    "INSERT INTO ai_query_testcase(question,gold_sql,datasource,difficulty,scenario,"
                    "form,expected_metric,tags,verified,enabled,dataset,is_deleted,"
                    "created_time,updated_time) "
                    "VALUES (:q,:s,:d,:df,:sc,:f,:em,'[]',true,true,:ds,false,now(),now())"),
                    {"q": q, "s": sql, "d": DS_CODE, "df": diff, "sc": scen, "f": form,
                     "em": metric, "ds": DATASET})
        ok += 1
        print("已写入：", q)
    print(f"\n完成：{ok} 题（dataset={DATASET}），跳过 {len(skipped)} 题")
    for q, why in skipped:
        print("  跳过：", q, "|", why)


asyncio.run(main())
