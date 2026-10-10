"""最小验证：① 指标匹配到了谁 ② 给标识符加引号后能否跑通。"""

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

QUESTIONS = [
    "所有燃煤合同的合同数量合计是多少？",
    "燃煤采购结算主表中，所有记录的合同单价平均值是多少？",
    "燃煤采购结算的平均合同单价是多少？",
]


async def main() -> None:
    from main import create_app

    create_app()
    from app.plugin.module_ai.query.service import (
        AiQueryService,
        _match_metric,
        _execute_custom_ds_sql,
    )

    metrics = await AiQueryService.list_metrics("ds:4")
    terms = await AiQueryService.list_terms("ds:4")

    for qt in QUESTIONS:
        m = _match_metric(qt, metrics, terms)
        print(f"Q: {qt}")
        print(f"   _match_metric → {m['key'] if m else None} "
              f"({m['name'] if m else '-'})  template={m['sql_template'] if m else '-'}")

    print()
    print("=== 最小验证：给标识符加双引号后再执行同一条模板 ===")
    for sql in (
        'SELECT SUM("BALANCEQTY") AS "结算总量" FROM "FUEL_CB_COALBALANCE"',
        'SELECT AVG("CONTRACTPRICE") AS "平均合同单价" FROM "FUEL_CB_COALBALANCE"',
        'SELECT AVG("LF") AS "平均干基全硫" FROM "DTXY_PMXX"',
    ):
        try:
            res = await _execute_custom_ds_sql(4, sql)
            print(f"  OK  {sql[:70]} → columns={res['columns']} rows={res['rows']}")
        except Exception as e:  # noqa: BLE001
            print(f"  ERR {sql[:70]} → {type(e).__name__}: {str(e)[:120]}")


asyncio.run(main())
