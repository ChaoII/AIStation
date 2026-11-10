"""燃料域（ds:4）补齐演示数据与本体能力（幂等，可重复执行）。

背景：2026-11-10 核查发现——
- `FUEL_CB_COALBALANCE` / `DETAIL` **0 行**，而「结算总量 / 平均合同单价」的指标与
  few-shot 示例正指向它 → 线上答 null（`ds4_missing_data_report.py` 已记录该缺口）；
- 同一指标 `total_settlement_qty` 又用 `FUEL_CMCS_INFACTORYBATCH.CHECKQTY` 兜底，
  **描述与 SQL 不一致**；
- 燃料对象上没有任何本体函数/动作（12 函数 + 15 动作全在视频域），Agent 本体工具为空。

本脚本做三件事（不改既有批次/化验数据，避免影响 fuel-v2 评测 gold）：
1. 往结算表插入 4 条演示数据（2026-08/09/10/11 各一条，ID 以 DEMO-BAL- 前缀可识别）；
2. 把「结算总量 / 平均合同单价」指标与 2 条 few-shot 示例统一到**结算表**口径；
3. 给燃料对象加 2 个本体函数 + 1 个动作（动作只允许改 REMARK）。

用法：
    cd backend
    uv run python scripts/seed_ds4_settlement_and_ontology_tools.py
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

# id, date, 结算数量, 合同单价, 含税煤款单价
SEED = [
    ("DEMO-BAL-202608", dt.date(2026, 8, 15), 1200, 520, 540),
    ("DEMO-BAL-202609", dt.date(2026, 9, 15), 1500, 535, 555),
    ("DEMO-BAL-202610", dt.date(2026, 10, 15), 1800, 548, 566),
    ("DEMO-BAL-202611", dt.date(2026, 11, 2), 900, 556, 575),
]

FUNCS = [
    {
        "code": "coal_settle_amount",
        "object_code": "coal_batch",
        "name": "结算金额（元）",
        "expr": "qty * price",
        "description": "结算数量 × 合同单价，算一批煤的结算金额",
        "parameters": [
            {"key": "qty", "type": "number", "label": "结算数量（吨）", "required": True},
            {"key": "price", "type": "number", "label": "合同单价（元/吨）", "required": True},
        ],
        "tool_description": "按结算数量与合同单价计算结算金额（元）",
    },
    {
        "code": "coal_ash_dry_basis",
        "object_code": "coal_assay",
        "name": "灰分折算（干燥基，%）",
        "expr": "ash_ad * 100 / (100 - mad)",
        "description": "把空干基灰分折算为干燥基灰分：Ad = Aad × 100 / (100 - Mad)",
        "parameters": [
            {"key": "ash_ad", "type": "number", "label": "空干基灰分 Aad（%）", "required": True},
            {"key": "mad", "type": "number", "label": "空干基水分 Mad（%）", "required": True},
        ],
        "tool_description": "按 Aad 与 Mad 计算干燥基灰分 Ad（%）",
    },
]

ACTS = [
    {
        "code": "coal_batch_annotate",
        "object_code": "coal_batch",
        "name": "给入厂批次加备注",
        "method": "update",
        "target_table": "FUEL_CMCS_INFACTORYBATCH",
        "white_fields": ["REMARK"],
        "parameters": [{"key": "REMARK", "type": "string", "label": "备注", "required": False}],
        "tool_description": "修改入厂煤批次的备注字段（只允许改 REMARK）",
    }
]


async def seed_settlement() -> None:
    from sqlalchemy import text

    from app.plugin.module_ai.query import executor as ex
    from app.plugin.module_ai.query import service as svc

    ds = await svc._load_ds(4)
    engine = ex.build_engine(svc._ds_cfg_from_model(ds))
    async with engine.begin() as conn:
        for id_, date, qty, cp, coalp in SEED:
            exists = (await conn.execute(
                text('SELECT 1 FROM "FUEL_CB_COALBALANCE" WHERE "ID"=:i'), {"i": id_}
            )).first()
            if exists:
                continue
            await conn.execute(
                text(
                    'INSERT INTO "FUEL_CB_COALBALANCE" '
                    '("ID","CREATIONTIME","BALANCEDATE","BALANCEQTY","CONTRACTPRICE",'
                    '"COALPRICE","MARGINQTY","ISDELETED") '
                    "VALUES (:i, now(), :d, :q, :cp, :coalp, 0, false)"
                ),
                {"i": id_, "d": date, "q": qty, "cp": cp, "coalp": coalp},
            )
    async with engine.connect() as conn:
        row = (await conn.execute(
            text('SELECT count(*), sum("BALANCEQTY") FROM "FUEL_CB_COALBALANCE"')
        )).fetchone()
    print(f"[settlement] rows={row[0]} sum_qty={row[1]}")


async def align_metrics() -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        await db.execute(text(
            "UPDATE ai_query_metrics SET "
            "sql_template='SELECT SUM(\"BALANCEQTY\") AS \"结算总量\" FROM \"FUEL_CB_COALBALANCE\" "
            "WHERE \"ISDELETED\" = false', "
            "description='燃煤结算主表中的结算数量合计' WHERE key='total_settlement_qty'"
        ))
        await db.execute(text(
            "UPDATE ai_query_metrics SET "
            "sql_template='SELECT AVG(\"CONTRACTPRICE\") AS \"平均合同单价\" FROM \"FUEL_CB_COALBALANCE\" "
            "WHERE \"CONTRACTPRICE\" IS NOT NULL', "
            "description='燃煤结算主表中的合同单价平均值' WHERE key='avg_contract_price'"
        ))
        await db.execute(text(
            "UPDATE ai_query_fewshot SET sql='SELECT SUM(\"BALANCEQTY\") AS 结算总量 "
            "FROM \"FUEL_CB_COALBALANCE\"' WHERE question LIKE '%结算总量%' AND datasource='ds:4'"
        ))
        await db.execute(text(
            "UPDATE ai_query_fewshot SET sql='SELECT SUM(\"RAILLOST\") AS 运损合计 "
            "FROM \"FUEL_CMCS_INFACTORYBATCH\"' WHERE question LIKE '%运损%' AND datasource='ds:4'"
        ))
    print("[metrics] aligned")


async def upsert_tools() -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        for f in FUNCS:
            if (await db.execute(text(
                "SELECT 1 FROM ai_ont_function WHERE code=:c AND is_deleted=false"), {"c": f["code"]}
            )).first():
                continue
            await db.execute(text(
                "INSERT INTO ai_ont_function(object_code,name,code,expr,description,parameters,"
                "tool_description,kind,is_deleted) "
                "VALUES (:oc,:n,:c,:e,:d,CAST(:p AS jsonb),:td,'expression',false)"
            ), {
                "oc": f["object_code"], "n": f["name"], "c": f["code"], "e": f["expr"],
                "d": f["description"], "p": json.dumps(f["parameters"], ensure_ascii=False),
                "td": f["tool_description"],
            })
        for a in ACTS:
            if (await db.execute(text(
                "SELECT 1 FROM ai_ont_action WHERE code=:c AND is_deleted=false"), {"c": a["code"]}
            )).first():
                continue
            await db.execute(text(
                "INSERT INTO ai_ont_action(object_code,name,code,method,target_table,white_fields,"
                "parameters,approval,status,visibility,is_deleted,tool_description) "
                "VALUES (:oc,:n,:c,:m,:t,CAST(:w AS jsonb),CAST(:p AS jsonb),false,"
                "'experimental','normal',false,:td)"
            ), {
                "oc": a["object_code"], "n": a["name"], "c": a["code"], "m": a["method"],
                "t": a["target_table"], "w": json.dumps(a["white_fields"]),
                "p": json.dumps(a["parameters"], ensure_ascii=False), "td": a["tool_description"],
            })
    print("[tools] functions/actions upserted")


async def verify() -> None:
    from types import SimpleNamespace

    from app.plugin.module_ai.ontology import agent_tools as T
    from app.plugin.module_ai.ontology import semantic as sem
    from app.plugin.module_ai.query import service as svc
    from app.plugin.module_ai.query.service import AiQueryService as QS

    sem.invalidate_semantic_cache()
    svc._SQL_CACHE.clear()
    auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
    for q in ("结算总量是多少", "平均合同单价是多少", "本月结算总量", "上个月结算总量"):
        ans = await QS.ask(q, auth, None, "ds:4")
        print(f"[ask] {q} | path={ans.get('path')} | rows={(ans.get('rows') or [])[:1]}")

    schemas, names = await T.build_selected_ontology_tools(
        ["coal_settle_amount", "coal_ash_dry_basis", "coal_batch_annotate"], user_id=1
    )
    print(f"[tool schemas] {len(schemas)} {sorted(names)}")
    # 注意：选定工具的运行时入口是 run_selected_ontology_tool（带 ont_fn__ 前缀）；
    # run_ontology_tool 走的是另一套「通用工具」命名，传前缀会报"未知本体工具"。
    out = await T.run_selected_ontology_tool(
        "ont_fn__coal_settle_amount", {"qty": 1200, "price": 520}, user_id=1)
    print(f"[call settle_amount] {str(out)[:120]}")
    out2 = await T.run_selected_ontology_tool(
        "ont_fn__coal_ash_dry_basis", {"ash_ad": 18.5, "mad": 8.0}, user_id=1)
    print(f"[call ash_dry] {str(out2)[:120]}")
    # 动作是「提议 → 确认」，这里只验证返回了确认载荷（不真的写业务库）
    act = await T.run_selected_ontology_tool(
        "ont_action__coal_batch_annotate", {"__k": "DEMO-BATCH", "REMARK": "联调"}, user_id=1)
    print(f"[action propose] {'confirm' if isinstance(act, dict) and '__action__' in act else act}")


async def main() -> None:
    from main import create_app

    create_app()
    await seed_settlement()
    await align_metrics()
    await upsert_tools()
    await verify()


if __name__ == "__main__":
    asyncio.run(main())
