"""火电厂（燃煤业务库 ds:4）业务概念种子。

补充 ``seed_power_plant_ontology.py`` 未覆盖的「业务概念」层：把散落在真实表与
指标里的燃煤业务概念（燃煤质量/供应商/采购合同/结算/运损扣吨/煤种/入厂批次/化验）
落成 ``ai_query_concept`` 行，供「数据与集成 → 业务概念」浏览与问数语义层使用。

数据源：``ds:4``（ezdcs_pg）。概念涉及的表均为该库真实存在的表。

用法（在 ``backend`` 下运行）::

    python scripts/seed_power_plant_concepts.py            # 幂等 upsert
    python scripts/seed_power_plant_concepts.py --dry-run  # 只看计划

幂等：按 name upsert（同一概念重跑不会重复插入）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

# 概念列表：每条概念的业务含义 + 关联真实表 + 可选指标编码（均基于 ds:4 真实资产）
CONCEPTS = [
    {"name": "燃煤质量", "synonyms": "煤质,热值,硫分,发热量", "metric_key": "avg_r",
     "tables": ["DTXY_PMXX", "FUEL_CMCS_ASSAY", "FUEL_CMCS_HEATASSAY", "FUEL_CMCS_SULFURASSAY"],
     "description": "燃煤质量指标：收到基低位发热量、干基全硫、灰分等，来源煤质分析与化验。"},
    {"name": "供应商", "synonyms": "供方,矿点,供应商矿点", "metric_key": "",
     "tables": ["FUEL_CMCS_SUPPLIER", "FUEL_CMCS_SUPPLIERMINE", "DTXY_GYSKDGX"],
     "description": "燃煤供应方及其矿点关系。"},
    {"name": "采购合同", "synonyms": "合同,单价,合同单价", "metric_key": "avg_contract_price",
     "tables": ["FUEL_CB_COALCONTRACT", "FUEL_CB_COALCONTRACTQUALITY"],
     "description": "燃煤采购合同与合同单价、质量约定。"},
    {"name": "结算", "synonyms": "结算量,结算,金额", "metric_key": "total_settlement_qty",
     "tables": ["FUEL_CB_COALBALANCE", "FUEL_CB_COALBALANCEDETAIL"],
     "description": "燃煤结算总量、结算明细与金额。"},
    {"name": "运损扣吨", "synonyms": "运损,扣吨,亏吨", "metric_key": "",
     "tables": ["FUEL_CB_COALBALANCEDETAIL"],
     "description": "运输损耗与到厂扣吨（结算明细中的运损/扣吨字段）。"},
    {"name": "煤种", "synonyms": "品名,煤种,煤类", "metric_key": "coal_fuelkind_count",
     "tables": ["FUEL_CMCS_FUELKIND", "DTXY_PMXX"],
     "description": "燃煤种类/品名。"},
    {"name": "入厂批次", "synonyms": "批次,入厂,批次数", "metric_key": "coal_batch_count",
     "tables": ["FUEL_CMCS_INFACTORYBATCH", "FUEL_CMCS_INFACTORYPLAN"],
     "description": "燃煤入厂批次与入厂计划。"},
    {"name": "化验", "synonyms": "化验单,煤质化验,化验结果", "metric_key": "coal_assay_count",
     "tables": ["FUEL_CMCS_ASSAY", "FUEL_CMCS_ASSAYCHECK", "FUEL_CMCS_PROXIMATEASSAY"],
     "description": "入厂煤化验单与工业分析、元素分析结果。"},
]


async def main(dry: bool) -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session

    if dry:
        print(f"[dry-run] 将 upsert {len(CONCEPTS)} 条业务概念（datasource=ds:4）:")
        for c in CONCEPTS:
            print(f"  - {c['name']}  tables={c['tables']}")
        return

    async with async_db_session.begin() as db:
        for c in CONCEPTS:
            await db.execute(
                text(
                    "INSERT INTO ai_query_concept"
                    "(name,description,synonyms,parent_name,domain,metric_key,tables,datasource) "
                    "VALUES (:n,:d,:s,'','',:m,:tb,'ds:4') "
                    "ON CONFLICT (name) DO UPDATE SET description=EXCLUDED.description, "
                    "synonyms=EXCLUDED.synonyms, metric_key=EXCLUDED.metric_key, "
                    "tables=EXCLUDED.tables, datasource=EXCLUDED.datasource, is_deleted=false"
                ),
                {"n": c["name"], "d": c["description"], "s": c["synonyms"],
                 "m": c["metric_key"], "tb": json.dumps(c["tables"], ensure_ascii=False)},
            )
    async with async_db_session() as db:
        rows = (
            await db.execute(
                text("SELECT datasource, count(*) FROM ai_query_concept "
                     "WHERE is_deleted=false GROUP BY 1")
            )
        ).fetchall()
        print("业务概念已落库，按数据源统计：", [(r[0], r[1]) for r in rows])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="燃煤业务概念种子")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划不写库")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
