"""燃煤场景数据种子（幂等，ds:4 燃煤业务库）。

把「数据与集成 + 治理」整条链路的示例数据统一成一套**燃料场景真实数据**：

1. 本体对象归属：支撑表属于 ds:4 的对象补 ``datasource_id=4``
   （历史数据里这些对象是 NULL，被当成系统对象，导致 DQ 扫不了、域里看不到）。
2. 管道：4 条「源表 → 本体对象」管道（源连接指向 ds:4，可直接「运行」落库）。
3. 数据域：删掉重复命名的「生产域」，建「燃料业务域」（成员表来自指标实际引用的表）。
4. ABAC：普通用户角色 A001 可查燃料业务表。
5. 交付命题（FDE）：入厂煤质量分析看板。
6. 动作（表级写回定义）：更新化验备注（FUEL_CMCS_ASSAY.REMARK）。
7. 筛选规则：ds:4 的系统表前缀/审计字段按燃料库真实命名配置
   （默认规则把 ``FUEL_`` 当系统表前缀、审计字段用下划线命名，对燃料库全不适用）。

用法::

    cd backend
    uv run python scripts/seed_fuel_scenario.py

前置：``ai_query_datasources`` 里已有 id=4 的燃煤业务库，且已同步过表结构。
"""
from __future__ import annotations

import asyncio
import json
import re

from sqlalchemy import text

from app.core.database import async_db_session

DS_ID = 4
DS_CODE = f"ds:{DS_ID}"

# 语义对象 code → 源表（必须是本体对象真实支撑表）
PIPELINES = [
    ("化验单入库", "FUEL_CMCS_ASSAY", "coal_assay",
     [{"from": "ID", "to": "ID"}, {"from": "ASSAYCODE", "to": "ASSAYCODE"},
      {"from": "ASSAYDATE", "to": "ASSAYDATE"}, {"from": "REMARK", "to": "REMARK"}]),
    ("入厂批次入库", "FUEL_CMCS_INFACTORYBATCH", "coal_batch",
     [{"from": "ID", "to": "ID"}, {"from": "BATCH", "to": "BATCH"},
      {"from": "SUPPLIERID", "to": "SUPPLIERID"}, {"from": "MINEID", "to": "MINEID"}]),
    ("矿点入库", "FUEL_CMCS_MINE", "coal_mine",
     [{"from": "ID", "to": "ID"}, {"from": "NAME", "to": "NAME"}]),
    ("煤种入库", "FUEL_CMCS_FUELKIND", "coal_fuelkind",
     [{"from": "ID", "to": "ID"}, {"from": "NAME", "to": "NAME"}]),
]

CORE_DOMAIN_TABLES = [
    "FUEL_CMCS_ASSAY", "FUEL_CMCS_INFACTORYBATCH", "FUEL_CMCS_MINE",
    "FUEL_CMCS_FUELKIND", "FUEL_CMCS_DISCHARGE", "FUEL_CMCS_FUELQUALITY",
    "FUEL_CB_COALCONTRACT", "FUEL_CB_QUALITYSETTING", "FUEL_CMCS_ASSAYCHECK",
]

FUEL_RULES = {
    "enabled": True,
    "system_table": {
        "prefixes": ["SYS_", "VIEW_", "V_", "JIMU_", "GEN_"],
        "keywords": ["_BAK", "_TEMP", "LOG", "HISTORY"],
        "exact": ["alembic_version", "apscheduler_jobs", "__EFMigrationsHistory"],
        "regex": "",
    },
    "audit_fields": [
        "CREATIONTIME", "LASTMODIFICATIONTIME", "CREATORUSERID", "LASTMODIFIERUSERID",
        "ISDELETED", "DELETERUSERID", "DELETIONTIME", "SYNCFLAG", "SYNCTIME",
        "ORGANIZATIONCODE",
    ],
}


async def _all_tables(db) -> set[str]:
    rows = (await db.execute(text(
        "SELECT table_name FROM ai_query_schema WHERE datasource=:d AND is_deleted=false"),
        {"d": DS_CODE})).fetchall()
    return {r[0] for r in rows}


async def main() -> None:  # pragma: no cover - 运维脚本
    async with async_db_session() as db:
        tables = await _all_tables(db)
        if not tables:
            raise SystemExit(f"{DS_CODE} 还没有同步表结构，请先「同步 schema」")
        obj_rows = (await db.execute(text(
            "SELECT code, backing_table FROM ai_ont_object "
            "WHERE is_deleted=false AND datasource_id=:i"), {"i": DS_ID})).fetchall()
        obj_table = {r[0]: r[1] for r in obj_rows}

        # 指标的 SQL 里实际引用的表（决定数据域成员与「域内指标」是否有数据）
        sqls = [r[0] or "" for r in (await db.execute(text(
            "SELECT sql_template FROM ai_query_metrics WHERE is_deleted=false AND datasource=:d"),
            {"d": DS_CODE})).fetchall()]
        used = [t for t in sorted(tables)
                if any(re.search(rf"\b{re.escape(t)}\b", s, re.I) for s in sqls)]
        domain_tables = list(dict.fromkeys(
            [t for t in CORE_DOMAIN_TABLES if t in tables] + used))

    async with async_db_session.begin() as db:
        # 1) 本体对象归属
        await db.execute(text(
            "UPDATE ai_ont_object o SET datasource_id=:i "
            "WHERE o.is_deleted=false AND o.datasource_id IS NULL "
            "AND coalesce(o.backing_table,'') <> '' "
            "AND EXISTS (SELECT 1 FROM ai_query_schema s WHERE s.datasource=:d "
            "            AND s.is_deleted=false "
            "            AND upper(s.table_name)=upper(o.backing_table))"),
            {"i": DS_ID, "d": DS_CODE})

        # 1.5) 无中文名的对象补个可读名（表名对象在域卡片上只会显示英文表名）
        await db.execute(text(
            "UPDATE ai_ont_object SET name='化验审核单' "
            "WHERE code='FUEL_CMCS_ASSAYCHECK' AND is_deleted=false AND name=code"))

        # 2) 管道
        for name, src, tgt, maps in PIPELINES:
            if tgt in obj_table and obj_table[tgt] != src:
                raise SystemExit(f"对象 {tgt} 的支撑表是 {obj_table[tgt]}，与脚本里的 {src} 不一致")
            await db.execute(text(
                "DELETE FROM ai_pipeline WHERE name=:n AND datasource=:d"),
                {"n": name, "d": DS_CODE})
            await db.execute(text(
                "INSERT INTO ai_pipeline(name,source_connection,source_table,target_object,"
                "mappings,enabled,datasource) VALUES (:n,:c,:s,:t,:m,true,:d)"),
                {"n": name, "c": str(DS_ID), "s": src, "t": tgt,
                 "m": json.dumps(maps, ensure_ascii=False), "d": DS_CODE})

        # 3) 数据域（「生产域」曾重复命名两条，删掉后一条并改名）
        await db.execute(text(
            "UPDATE ai_data_domain SET is_deleted=true "
            "WHERE name='生产域' AND id=(SELECT max(id) FROM ai_data_domain WHERE name='生产域' AND is_deleted=false)"))
        await db.execute(text(
            "UPDATE ai_data_domain SET name='视频监控域', code='video', "
            "description='摄像头/告警/训练任务等监控生产数据' WHERE name='生产域' AND is_deleted=false"))
        await db.execute(text("DELETE FROM ai_data_domain WHERE name='燃料业务域'"))
        await db.execute(text(
            "INSERT INTO ai_data_domain(name,code,description,tables,members,enabled) "
            "VALUES (:n,:c,:d,:t,:m,true)"),
            {"n": "燃料业务域", "c": "fuel",
             "d": "入厂煤检质、计量、采购与结算相关业务表（燃煤业务库 ds:4）",
             "t": json.dumps(domain_tables, ensure_ascii=False),
             "m": json.dumps([1, 2])})

        # 4) ABAC
        await db.execute(text("DELETE FROM ai_access_rule WHERE name='燃料业务可查'"))
        await db.execute(text(
            "INSERT INTO ai_access_rule(name,attribute,value,allowed_tables,sensitive_ok,enabled) "
            "VALUES (:n,'role','A001',:t,false,true)"),
            {"n": "燃料业务可查",
             "t": json.dumps(domain_tables[:6], ensure_ascii=False)})

        # 5) 交付命题
        await db.execute(text(
            "DELETE FROM ai_delivery_proposition WHERE title='入厂煤质量分析看板'"))
        await db.execute(text(
            "INSERT INTO ai_delivery_proposition(title,description,criteria,owner,"
            "step_diagnosis,step_modeling,step_assembly,step_shadow,step_handover,gap,"
            "delivery_assets,status,shadow_metric,shadow_golden,shadow_tolerance) "
            "VALUES (:ti,:de,:cr,'燃料管理部','done','done','done','todo','todo',:gap,:da,"
            "'open',:sm,:sg,:st)"),
            {"ti": "入厂煤质量分析看板",
             "de": "基于入厂煤批次、化验单与矿点数据，按矿点/煤种统计热值、硫分等质量指标",
             "cr": "按矿点与煤种的热值、硫分月度趋势可查，口径与化验单一致",
             "gap": json.dumps(["灰熔融性化验数据覆盖不全"], ensure_ascii=False),
             "da": json.dumps(["FUEL_CMCS_ASSAY", "FUEL_CMCS_INFACTORYBATCH",
                               "FUEL_CMCS_MINE", "FUEL_CMCS_FUELKIND"], ensure_ascii=False),
             "sm": "avg_r", "sg": "0.98", "st": "0.03"})

        # 6) 动作（表级写回定义，不执行）
        await db.execute(text("DELETE FROM ai_query_writeback WHERE name='更新化验备注'"))
        await db.execute(text(
            "INSERT INTO ai_query_writeback(name,object_table,writable_cols,validation,"
            "approve,enabled,writable_by_role) VALUES (:n,:ot,:wc,'必填、长度<=200',true,true,:r)"),
            {"n": "更新化验备注", "ot": "FUEL_CMCS_ASSAY",
             "wc": json.dumps(["REMARK"], ensure_ascii=False),
             "r": json.dumps([], ensure_ascii=False)})

        # 7) 筛选规则
        await db.execute(text(
            "UPDATE ai_query_datasources SET filter_rules=:r WHERE id=:i"),
            {"r": json.dumps(FUEL_RULES, ensure_ascii=False), "i": DS_ID})

    print(f"燃料场景种子完成：管道 4 条 / 数据域 1 个（{len(domain_tables)} 张表）/ "
          "ABAC 1 条 / FDE 1 条 / 动作 1 条")


asyncio.run(main())
