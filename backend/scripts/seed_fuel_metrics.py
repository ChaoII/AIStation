"""修复/补齐燃煤业务库（ds:4）的指标 SQL，保证「问数」真能出数。

背景（实测）：
- `AVG(RZ)` / `AVG(LF)`：列是 **varchar**，Postgres 没有 avg(varchar) → 快路径必失败；
- `FROM DTXY_PMXX` / `FROM FUEL_CB_COALBALANCE`：未加引号的大写表名会被折叠成小写 →
  `relation "dtxy_pmxx" does not exist`；
- `FUEL_CB_COALBALANCE` 在本库**0 行** → 结算类指标即使 SQL 正确也只能答 NULL，
  改用同义、且有真实数据的表（入厂批次 `CHECKQTY` 验收量 / `VIEW_GETBATCHPRICE` 合同价）；
- 「路损（运损）」在入厂批次表里是真实列 `RAILLOST`，但没有对应指标，导致问「运损合计」
  只能靠 NL2SQL 现算；补一条 `fuel_raillost_total` 并把术语「运损」绑上去。

用法::

    cd backend
    uv run python scripts/fix_fuel_metrics.py
"""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import text

from app.core.database import async_db_session
from app.plugin.module_ai.query import executor as _ex

DS_CODE = "ds:4"

#: key -> (新 SQL, 单位)
FIXED_SQL: dict[str, tuple[str, str]] = {
    "total_settlement_qty": (
        'SELECT SUM("CHECKQTY") AS "结算总量" FROM "FUEL_CMCS_INFACTORYBATCH"', "吨"),
    "avg_contract_price": (
        'SELECT AVG(CAST("CONTRACTPRICE" AS numeric)) AS "平均合同单价" '
        'FROM "VIEW_GETBATCHPRICE" WHERE "CONTRACTPRICE" IS NOT NULL', "元/吨"),
    "avg_rz": (
        'SELECT AVG(CAST("RZ" AS numeric)) AS "平均收到基低位发热量" '
        'FROM "DTXY_PMXX" WHERE "RZ" IS NOT NULL', "Kcal/kg"),
    "avg_lf": (
        'SELECT AVG(CAST("LF" AS numeric)) AS "平均干基全硫" '
        'FROM "DTXY_PMXX" WHERE "LF" IS NOT NULL', "%"),
}

#: 新增指标（key -> key/name/desc/sql/unit/agg）
NEW_METRICS: list[dict] = [
    {
        "key": "fuel_raillost_total",
        "name": "运损合计",
        "description": "入厂煤批次的路损（运损）合计",
        "sql_template": 'SELECT SUM(CAST("RAILLOST" AS numeric)) AS "运损合计" '
                        'FROM "FUEL_CMCS_INFACTORYBATCH"',
        "unit": "吨",
        "agg": "sum",
    },
]

#: 术语 → 指标绑定（term -> metric_key）
TERM_BIND: dict[str, str] = {
    "运损": "fuel_raillost_total",
    # 「验收量」是入厂批次表里的结算依据列（CHECKQTY）；没有这条绑定，
    # 「入厂煤的验收量合计」会被「入厂煤批次数量」抢答（实测 277 vs 4294961）。
    "验收量": "total_settlement_qty",
    "结算量": "total_settlement_qty",
}

#: 补充 few-shot（问 → SQL）：分组/联表/CASET 这类容易写错的口径，用人审过的示例固化石。
#: 插入前先真跑一遍，跑不通的不入库（避免把错题沉淀成"标准答案"）。
FEWSHOTS: list[tuple[str, str]] = [
    ("各煤种的平均干基全硫是多少？",
     'SELECT "COALTYPE" AS "煤种", ROUND(AVG(CAST("LF" AS numeric))::numeric, 2) AS "平均干基全硫" '
     'FROM "DTXY_PMXX" WHERE "LF" IS NOT NULL GROUP BY "COALTYPE" ORDER BY "平均干基全硫" DESC'),
    ("各煤种的平均收到基低位发热量是多少？",
     'SELECT "COALTYPE" AS "煤种", ROUND(AVG(CAST("RZ" AS numeric))::numeric, 2) AS "平均收到基低位发热量" '
     'FROM "DTXY_PMXX" WHERE "RZ" IS NOT NULL GROUP BY "COALTYPE" ORDER BY "平均收到基低位发热量" DESC'),
    ("按矿点统计入厂煤批次数量",
     'SELECT COALESCE(m."NAME", \'未关联矿点\') AS "矿点", COUNT(b."ID") AS "批次数" '
     'FROM "FUEL_CMCS_INFACTORYBATCH" b LEFT JOIN "FUEL_CMCS_MINE" m ON m."ID" = b."MINEID" '
     'GROUP BY 1 ORDER BY "批次数" DESC'),
    ("运损和扣吨合计是多少？",
     'SELECT SUM(CAST("RAILLOST" AS numeric)) AS "运损合计", '
     'SUM(CAST("MARGINQTY" AS numeric)) AS "盈亏量合计" FROM "FUEL_CMCS_INFACTORYBATCH"'),
    ("最近一个月平均收到基低位发热量是多少？",
     'SELECT ROUND(AVG(CAST(q."RZ" AS numeric))::numeric, 2) AS "平均收到基低位发热量" '
     'FROM "DTXY_PMXX" q WHERE q."RZ" IS NOT NULL '
     'AND q."CREATIONTIME" >= CURRENT_DATE - INTERVAL \'1 month\''),
]


async def _ds_cfg() -> dict:
    async with async_db_session() as db:
        r = (await db.execute(text(
            "SELECT type,host,port,database,username,password "
            "FROM ai_query_datasources WHERE id=4"))).fetchone()
    return {"type": r[0], "host": r[1], "port": r[2], "database": r[3],
            "username": r[4], "password": r[5]}


async def main() -> None:  # pragma: no cover - 运维脚本
    async with async_db_session.begin() as db:
        for key, (sql, unit) in FIXED_SQL.items():
            r = await db.execute(text(
                "UPDATE ai_query_metrics SET sql_template=:s, unit=:u, updated_time=now() "
                "WHERE key=:k AND datasource=:d AND is_deleted=false"),
                {"s": sql, "u": unit, "k": key, "d": DS_CODE})
            print(f"修指标 {key}: {r.rowcount} 行")

        for m in NEW_METRICS:
            exists = (await db.execute(text(
                "SELECT id FROM ai_query_metrics WHERE key=:k AND datasource=:d AND is_deleted=false"),
                {"k": m["key"], "d": DS_CODE})).scalar()
            if exists:
                await db.execute(text(
                    "UPDATE ai_query_metrics SET name=:n, description=:de, sql_template=:s, "
                    "unit=:u, agg=:a, enabled=true, updated_time=now() WHERE id=:i"),
                    {"n": m["name"], "de": m["description"], "s": m["sql_template"],
                     "u": m["unit"], "a": m["agg"], "i": exists})
                print(f"更新指标 {m['key']}")
            else:
                await db.execute(text(
                    "INSERT INTO ai_query_metrics(datasource,key,name,description,sql_template,"
                    "params,dimensions,agg,unit,enabled,sort,cache_ttl,status,uuid,is_deleted,"
                    "created_time,updated_time) "
                    "VALUES (:d,:k,:n,:de,:s,'[]','[]',:a,:u,true,0,0,'0',:uuid,false,now(),now())"),
                    {"d": DS_CODE, "k": m["key"], "n": m["name"], "de": m["description"],
                     "s": m["sql_template"], "a": m["agg"], "u": m["unit"],
                     "uuid": uuid.uuid4().hex})
                print(f"新增指标 {m['key']}")

        for term, mkey in TERM_BIND.items():
            r = await db.execute(text(
                "UPDATE ai_query_dictionary SET metric_key=:mk, updated_time=now() "
                "WHERE term=:t AND datasource=:d AND is_deleted=false"),
                {"mk": mkey, "t": term, "d": DS_CODE})
            if not r.rowcount:
                # 词典里还没有这个词 → 新增（否则「绑定了但词不在」等于没绑）
                await db.execute(text(
                    "INSERT INTO ai_query_dictionary(datasource,term,metric_key,field_path,type,"
                    "uuid,status,is_deleted,created_time,updated_time) "
                    "VALUES (:d,:t,:mk,'','term',:uuid,'0',false,now(),now())"),
                    {"d": DS_CODE, "t": term, "mk": mkey, "uuid": uuid.uuid4().hex})
                print(f"新增术语 {term} → {mkey}")
            else:
                print(f"绑定术语 {term} → {mkey}: {r.rowcount} 行")

    # few-shot：先真跑校验，再幂等写入
    cfg = await _ds_cfg()
    for q, sql in FEWSHOTS:
        try:
            await _ex.execute_select(cfg, sql)
        except Exception as e:  # noqa: BLE001
            print(f"跳过示例（SQL 跑不通）：{q} -> {str(e)[:100]}")
            continue
        async with async_db_session.begin() as db:
            exists = (await db.execute(text(
                "SELECT id FROM ai_query_fewshot WHERE datasource=:d AND question=:q "
                "AND is_deleted=false"), {"d": DS_CODE, "q": q})).scalar()
            if exists:
                await db.execute(text(
                    "UPDATE ai_query_fewshot SET sql=:s, enabled=true, updated_time=now() "
                    "WHERE id=:i"), {"s": sql, "i": exists})
            else:
                await db.execute(text(
                    "INSERT INTO ai_query_fewshot(datasource,question,sql,enabled,uuid,status,"
                    "is_deleted,created_time,updated_time) "
                    "VALUES (:d,:q,:s,true,:uuid,'0',false,now(),now())"),
                    {"d": DS_CODE, "q": q, "s": sql, "uuid": uuid.uuid4().hex})
        print(f"示例已写入：{q}")

    # 体检：逐条真跑一遍，打印失败/空结果
    async with async_db_session() as db:
        mets = (await db.execute(text(
            "SELECT key,name,sql_template FROM ai_query_metrics "
            "WHERE is_deleted=false AND datasource=:d AND enabled=true AND "
            "(sql_template IS NOT NULL AND sql_template <> '') ORDER BY id"), {"d": DS_CODE})).fetchall()
    ok = empty = fail = 0
    bad: list[tuple[str, str]] = []
    for key, _name, sql in mets:
        if not str(sql).lstrip().lower().startswith("select"):
            continue
        try:
            out = await _ex.execute_select(cfg, sql)
        except Exception as e:  # noqa: BLE001
            fail += 1
            bad.append((key, str(e).split("：", 1)[-1][:80]))
            continue
        rows = out.get("rows") or []
        if not rows or all(all(v is None for v in row) for row in rows):
            empty += 1
            bad.append((key, "空结果"))
        else:
            ok += 1
    print(f"\n指标体检：成功 {ok} / 空 {empty} / 失败 {fail}")
    for k, why in bad[:10]:
        print("  -", k, "|", why)


asyncio.run(main())
