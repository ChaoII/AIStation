"""为 ds:4 播种 few-shot 示例（示范"大写表名/列名必须加双引号"等约定）。

每条示例都**先在目标库执行验证**，跑不通的直接跳过 —— 不允许把坏示例喂给模型。

用法（backend 下）::

    python scripts/seed_ds4_fewshots.py --dry-run
    python scripts/seed_ds4_fewshots.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DS = "ds:4"

#: (问题, 金标 SQL, 说明)。重点是**双引号约定**与常见形状（单表聚合/分组/去重/联表/时间窗口/指标口径）
EXAMPLES: list[tuple[str, str, str]] = [
    ("化验记录一共有多少条？",
     'SELECT COUNT(*) AS 化验记录数 FROM "FUEL_CMCS_ASSAY"',
     "单表计数：大写表名必须加双引号"),
    ("煤质记录一共有多少条？",
     'SELECT COUNT(*) AS 煤质记录数 FROM "DTXY_PMXX"',
     "单表计数"),
    ("按煤种类型统计各有多少条煤质记录？",
     'SELECT "COALTYPE" AS 煤种类型, COUNT(*) AS 记录数 FROM "DTXY_PMXX" '
     "GROUP BY \"COALTYPE\" ORDER BY 记录数 DESC",
     "分组统计：分组列也要加双引号"),
    ("一共有多少种品名？",
     'SELECT COUNT(DISTINCT "VARIETY") AS 品名数 FROM "DTXY_PMXX"',
     "去重计数"),
    ("每条皮带路线各有多少条流向记录？",
     'SELECT t."LINENAME" AS 皮带路线, COUNT(f."ID") AS 流向条数 FROM "FUEL_CMCS_BELTLINE" t '
     'LEFT JOIN "FUEL_CMCS_BELTLINEFLOW" f ON f."BELTLINEID" = t."ID" '
     "GROUP BY t.\"LINENAME\" ORDER BY 流向条数 DESC",
     "联表：按本体关系 BELTLINEFLOW.BELTLINEID → BELTLINE.ID"),
    ("化验记录按月份统计数量走势",
     'SELECT TO_CHAR("ASSAYDATE", \'YYYY-MM\') AS 月份, COUNT(*) AS 化验数 '
     'FROM "FUEL_CMCS_ASSAY" GROUP BY 月份 ORDER BY 月份',
     "时间窗口：日期截断到月"),
    ("结算总量是多少？",
     'SELECT SUM("BALANCEQTY") AS 结算总量 FROM "FUEL_CB_COALBALANCE"',
     "指标口径：结算量取 BALANCEQTY 合计"),
    ("运损合计是多少？",
     'SELECT SUM("RAILLOST") AS 运损合计 FROM "FUEL_CB_COALBALANCEDETAIL"',
     "指标口径：运损取 RAILLOST 合计"),
    ("燃煤合同的合同数量合计是多少？",
     'SELECT SUM("CONTRACTAMOUNT") AS 合同数量合计 FROM "FUEL_CB_COALCONTRACT"',
     "合同数量取 CONTRACTAMOUNT（注意与结算量 BALANCEQTY 区分）"),
    # ---- 弱项形式（实测：窗口函数 0%、多维报表 33%、排名TopN 60%）----
    ("按煤种类型统计记录数并排名",
     'SELECT "COALTYPE" AS 煤种类型, COUNT(*) AS 记录数, '
     'RANK() OVER (ORDER BY COUNT(*) DESC) AS 排名 FROM "DTXY_PMXX" '
     "GROUP BY \"COALTYPE\" ORDER BY 排名",
     "排名：RANK() OVER (ORDER BY 聚合列 DESC)"),
    ("化验记录最多的前 3 个品名",
     'SELECT "VARIETY" AS 品名, COUNT(*) AS 记录数 FROM "DTXY_PMXX" '
     "GROUP BY \"VARIETY\" ORDER BY 记录数 DESC LIMIT 3",
     "TopN：GROUP BY + ORDER BY 聚合列 DESC + LIMIT"),
    ("按月份统计化验数并给出累计值",
     'SELECT TO_CHAR("ASSAYDATE", \'YYYY-MM\') AS 月份, COUNT(*) AS 化验数, '
     'SUM(COUNT(*)) OVER (ORDER BY TO_CHAR("ASSAYDATE", \'YYYY-MM\')) AS 累计化验数 '
     'FROM "FUEL_CMCS_ASSAY" GROUP BY 月份 ORDER BY 月份',
     "窗口累计：SUM(聚合) OVER (ORDER BY 维度)"),
    ("按煤种类型和品名统计记录数",
     'SELECT "COALTYPE" AS 煤种类型, "VARIETY" AS 品名, COUNT(*) AS 记录数 '
     'FROM "DTXY_PMXX" GROUP BY "COALTYPE", "VARIETY" ORDER BY 记录数 DESC',
     "多维报表：多列 GROUP BY，每列都加双引号"),
    ("各煤种类型的记录占比是多少",
     'SELECT "COALTYPE" AS 煤种类型, '
     'ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS 占比 FROM "DTXY_PMXX" '
     "GROUP BY \"COALTYPE\" ORDER BY 占比 DESC",
     "占比：COUNT(*)*100.0 / SUM(COUNT(*)) OVER ()"),
]


async def main(dry: bool) -> None:
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.service import _execute_custom_ds_sql

    ds_id = int(DS.split(":")[-1])
    async with async_db_session() as db:
        have = {
            r[0]
            for r in (
                await db.execute(
                    text(
                        "SELECT question FROM ai_query_fewshot "
                        "WHERE is_deleted=false AND datasource=:d"
                    ),
                    {"d": DS},
                )
            ).fetchall()
        }
    print(f"ds:4 现有 few-shot: {len(have)} 条")

    accepted, skipped = [], []
    for q, sql, desc in EXAMPLES:
        if q in have:
            print(f"  已存在，跳过：{q}")
            continue
        try:
            res = await _execute_custom_ds_sql(ds_id, sql)
            accepted.append((q, sql, desc, len(res.get("rows") or [])))
        except Exception as e:  # noqa: BLE001
            skipped.append((q, str(e)[:110]))

    print(f"验证通过 {len(accepted)} 条，跳过 {len(skipped)} 条")
    for q, sql, desc, n in accepted:
        print(f"  + {q}  （返回 {n} 行）")
    for q, err in skipped:
        print(f"  - 跳过 {q}: {err}")

    if dry:
        print("\n[dry-run] 未写入")
        return
    if not accepted:
        print("没有可写入的示例")
        return
    async with async_db_session.begin() as db:
        for q, sql, desc, _ in accepted:
            await db.execute(
                text(
                    "INSERT INTO ai_query_fewshot(datasource,question,sql,enabled,description,"
                    "status,uuid,is_deleted,created_time,updated_time) "
                    "VALUES(:d,:q,:s,true,:desc,'0',:u,false,now(),now())"
                ),
                {"d": DS, "q": q, "s": sql, "desc": desc, "u": uuid.uuid4().hex},
            )
    print(f"\n已写入 {len(accepted)} 条 ds:4 few-shot")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.dry_run))
