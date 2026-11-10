"""本地副本（ezdcs_yuanmei / ds:6）业务数据补齐 + 问数元数据克隆。

背景：远程 ds:4 是只读业务快照，缺合同、采样制样明细、细项化验、计划等模块。
2026-11-10 已用 pg_dump/pg_restore 在本地 PG 新建 `ezdcs_yuanmei` 副本，
本脚本只对**本地副本**写入演示数据，不碰远程库，因此不影响 fuel-v2 评测基准。

幂等：全部按 `DEMO-` 前缀主键 + `ON CONFLICT (ID) DO NOTHING`，可重复执行。

用法：
    cd backend
    uv run python scripts/seed_local_copy_business_data.py
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import random
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DS_CODE = "ezdcs_local"
RNG = random.Random(20261110)

# ds:6 专用指标（只写副本，不写 ds:4，避免影响评测基准）
EXTRA_METRICS = [
    ("contract_amount_sum", "合同数量合计", "燃煤采购合同主表中合同数量（CONTRACTAMOUNT）合计",
     'SELECT SUM("CONTRACTAMOUNT") AS "合同数量合计" FROM "FUEL_CB_COALCONTRACT" WHERE "ISDELETED" = false',
     "sum", "吨"),
    ("contract_avg_price", "合同平均单价", "燃煤采购合同主表中的合同单价平均值",
     'SELECT AVG("CONTRACTPRICE") AS "合同平均单价" FROM "FUEL_CB_COALCONTRACT" '
     'WHERE "CONTRACTPRICE" IS NOT NULL', "avg", "元/吨"),
    ("sampling_count", "采样单数", "入厂煤采样单（FUEL_CMCS_RCSAMPLING）数量",
     'SELECT COUNT(*) AS "采样单数" FROM "FUEL_CMCS_RCSAMPLING" WHERE "ISDELETED" = false',
     "count", "单"),
    ("make_count", "制样单数", "入厂煤制样单（FUEL_CMCS_MAKE）数量",
     'SELECT COUNT(*) AS "制样单数" FROM "FUEL_CMCS_MAKE" WHERE "ISDELETED" = false',
     "count", "单"),
    ("assay_sulfur_avg", "化验平均干基全硫", "硫分化验（FUEL_CMCS_SULFURASSAY）STAD 平均值",
     'SELECT ROUND(AVG("STAD")::numeric, 3) AS "化验平均干基全硫" '
     'FROM "FUEL_CMCS_SULFURASSAY" WHERE "ISDELETED" = false', "avg", "%"),
    ("assay_heat_avg", "化验平均发热量", "热值化验（FUEL_CMCS_HEATASSAY）QBAD 平均值",
     'SELECT ROUND(AVG("QBAD")::numeric, 2) AS "化验平均发热量" '
     'FROM "FUEL_CMCS_HEATASSAY" WHERE "ISDELETED" = false', "avg", "Kcal/kg"),
    ("plan_year_in_qty", "年度计划进煤量", "年度计划（FUEL_CMCS_PLANYEAR）当年计划进煤量",
     'SELECT SUM("INCOALQTY") AS "年度计划进煤量" FROM "FUEL_CMCS_PLANYEAR" '
     'WHERE "ISDELETED" = false AND "YEAR" = EXTRACT(YEAR FROM CURRENT_DATE)', "sum", "吨"),
    ("plan_month_in_qty", "月度计划进煤量", "月度计划（FUEL_CMCS_PLANMONTH）当月计划进煤量",
     'SELECT SUM("INCOALQTY") AS "月度计划进煤量" FROM "FUEL_CMCS_PLANMONTH" '
     'WHERE "ISDELETED" = false AND "PLANDATE" >= date_trunc(\'month\', CURRENT_DATE) '
     'AND "PLANDATE" < date_trunc(\'month\', CURRENT_DATE) + INTERVAL \'1 month\'', "sum", "吨"),
]


def D(v: float) -> Decimal:
    return Decimal(str(round(v, 2)))


async def _engine():
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query import executor as ex
    from app.plugin.module_ai.query import service as svc

    async with async_db_session() as db:
        ds_id = (await db.execute(text(
            "SELECT id FROM ai_query_datasources WHERE code=:c AND is_deleted=false"
        ), {"c": DS_CODE})).scalar()
    if not ds_id:
        raise SystemExit(f"找不到数据源 {DS_CODE}")
    ds = await svc._load_ds(int(ds_id))
    return ex.build_engine(svc._ds_cfg_from_model(ds)), int(ds_id)


async def _bulk(conn, table: str, rows: list[dict]) -> int:
    from sqlalchemy import text

    if not rows:
        return 0
    cols = list(rows[0].keys())
    sql = (
        f'INSERT INTO "{table}" (' + ",".join(f'"{c}"' for c in cols) + ") VALUES ("
        + ",".join(f":{c}" for c in cols) + ') ON CONFLICT ("ID") DO NOTHING'
    )
    await conn.execute(text(sql), rows)
    return len(rows)


async def clone_query_meta(ds_id: int) -> None:
    """把 ds:4 的指标/术语/概念/示例复制到 ds:6（否则副本没有快路径）。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    target = f"ds:{ds_id}"
    async with async_db_session.begin() as db:
        await db.execute(text(
            "WITH t(ds) AS (SELECT CAST(:t AS varchar)) "
            "INSERT INTO ai_query_metrics(datasource,key,name,description,sql_template,params,dimensions,"
            "agg,unit,permission_tag,enabled,sort,cache_ttl,is_deleted,uuid,status,created_time,updated_time,"
            "object_code,property_code,agg_fn,bound_dimensions) "
            "SELECT t.ds,key,name,description,sql_template,params,dimensions,agg,unit,permission_tag,enabled,"
            "sort,cache_ttl,false,gen_random_uuid(),'0',now(),now(),object_code,property_code,agg_fn,bound_dimensions "
            "FROM ai_query_metrics, t WHERE ai_query_metrics.datasource='ds:4' AND is_deleted=false "
            "AND NOT EXISTS (SELECT 1 FROM ai_query_metrics m WHERE m.datasource=t.ds "
            "AND m.key=ai_query_metrics.key AND m.is_deleted=false)"
        ), {"t": target})
        await db.execute(text(
            "WITH t(ds) AS (SELECT CAST(:t AS varchar)) "
            "INSERT INTO ai_query_dictionary(datasource,term,metric_key,field_path,type,is_deleted,"
            "uuid,status,created_time,updated_time) "
            "SELECT t.ds,term,metric_key,field_path,type,false,gen_random_uuid(),'0',now(),now() "
            "FROM ai_query_dictionary, t WHERE ai_query_dictionary.datasource='ds:4' AND is_deleted=false "
            "AND NOT EXISTS (SELECT 1 FROM ai_query_dictionary d WHERE d.datasource=t.ds "
            "AND d.term=ai_query_dictionary.term AND d.is_deleted=false)"
        ), {"t": target})
        await db.execute(text(
            "WITH t(ds) AS (SELECT CAST(:t AS varchar)) "
            "INSERT INTO ai_query_fewshot(datasource,question,sql,enabled,is_deleted,"
            "uuid,status,created_time,updated_time) "
            "SELECT t.ds,question,sql,true,false,gen_random_uuid(),'0',now(),now() "
            "FROM ai_query_fewshot, t WHERE ai_query_fewshot.datasource='ds:4' AND is_deleted=false "
            "AND NOT EXISTS (SELECT 1 FROM ai_query_fewshot f WHERE f.datasource=t.ds "
            "AND f.question=ai_query_fewshot.question AND f.is_deleted=false)"
        ), {"t": target})
        # 概念表 name 是全局唯一（不是 datasource+name），无法为副本复制同名概念；
        # 指标名/术语/示例已足够支撑快路径，概念跳过。
    print(f"[meta] 指标/术语/示例已克隆到 {target}（概念按 name 全局唯一，跳过）")


async def seed_extra_metrics(ds_id: int) -> None:
    """ds:6 专用指标（合同/采样制样/细项化验/计划），不写 ds:4。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    target = f"ds:{ds_id}"
    async with async_db_session.begin() as db:
        for key, name, desc, sql, agg, unit in EXTRA_METRICS:
            found = (await db.execute(text(
                "SELECT 1 FROM ai_query_metrics WHERE datasource=:d AND key=:k AND is_deleted=false"
            ), {"d": target, "k": key})).first()
            if found:
                await db.execute(text(
                    "UPDATE ai_query_metrics SET name=:n, description=:ds, sql_template=:s, agg=:a, unit=:u "
                    "WHERE datasource=:d AND key=:k"
                ), {"n": name, "ds": desc, "s": sql, "a": agg, "u": unit, "d": target, "k": key})
            else:
                await db.execute(text(
                    "INSERT INTO ai_query_metrics(datasource,key,name,description,sql_template,params,"
                    "dimensions,agg,unit,permission_tag,enabled,sort,cache_ttl,is_deleted,uuid,status,"
                    "created_time,updated_time) VALUES (:d,:k,:n,:ds,:s,'[]'::jsonb,'[]'::jsonb,:a,:u,"
                    "'',true,0,0,false,gen_random_uuid(),'0',now(),now())"
                ), {"d": target, "k": key, "n": name, "ds": desc, "s": sql, "a": agg, "u": unit})
    print(f"[meta] 副本专用指标 {len(EXTRA_METRICS)} 个已就绪")


async def seed_business(conn) -> None:
    from sqlalchemy import text

    # ---------- 参考数据（来自副本已有业务表） ----------
    suppliers = (await conn.execute(text(
        'SELECT "ID","NAME" FROM "FUEL_CMCS_SUPPLIER" WHERE "ISDELETED"=false ORDER BY "ID" LIMIT 30'
    ))).fetchall()
    mines = (await conn.execute(text(
        'SELECT "ID","NAME" FROM "FUEL_CMCS_MINE" WHERE "ISDELETED"=false ORDER BY "ID" LIMIT 30'
    ))).fetchall()
    kinds = (await conn.execute(text(
        'SELECT "ID","NAME" FROM "FUEL_CMCS_FUELKIND" WHERE "ISDELETED"=false ORDER BY "ID" LIMIT 20'
    ))).fetchall()
    template_id = (await conn.execute(text(
        'SELECT "ID" FROM "FUEL_CB_CONTRACTTEMPLANTE" WHERE "ISDELETED"=false ORDER BY "ID" LIMIT 1'
    ))).scalar()
    batches = (await conn.execute(text(
        'SELECT "ID","BATCH","FACTARRIVEDATE" FROM "FUEL_CMCS_INFACTORYBATCH" '
        'WHERE "ISDELETED"=false ORDER BY "FACTARRIVEDATE" DESC LIMIT 500'
    ))).fetchall()
    assays = (await conn.execute(text(
        'SELECT "ID","ASSAYCODE","ASSAYDATE" FROM "FUEL_CMCS_ASSAY" '
        'WHERE "ISDELETED"=false ORDER BY "ASSAYDATE" DESC LIMIT 500'
    ))).fetchall()
    if not suppliers or not mines or not kinds or not batches or not assays:
        raise SystemExit("参考表为空，无法补数")
    print(f"[ref] suppliers={len(suppliers)} mines={len(mines)} kinds={len(kinds)} "
          f"batches={len(batches)} assays={len(assays)} template={bool(template_id)}")

    # ---------- 1. 采购合同 + 质量约束 + 模板量价条款 ----------
    contracts, quality, temp_items = [], [], []
    for i in range(1, 41):
        cid = f"DEMO-CT-{i:03d}"
        amount = RNG.randint(20000, 80000)
        price = RNG.randint(480, 620)
        sign = dt.datetime(2025, 12, 20) + dt.timedelta(days=(i - 1) * 8)
        sid, sname = suppliers[(i - 1) % len(suppliers)]
        mine_name = mines[(i - 1) % len(mines)][1]
        kind_name = kinds[(i - 1) % len(kinds)][1]
        monthly = {m: amount // 12 for m in
                   ("JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
                    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER")}
        row = {
            "ID": cid, "CREATIONTIME": sign, "SIGNDATE": sign,
            "CONTRACTNUM": f"HT2026{i:04d}", "CONTRACTTYPE": "长协煤" if i % 2 else "市场煤",
            "CONTRACTAMOUNT": D(amount), "CONTRACTPRICE": D(price),
            "CONTRACTFREIGHT": D(RNG.randint(20, 60)), "PETTYPRICE": D(RNG.randint(5, 15)),
            "SUPPLIERID": sid, "MINENAMES": mine_name, "MINEIDS": mines[(i - 1) % len(mines)][0],
            "FUELKINDNAMES": kind_name, "FUELKINDIDS": kinds[(i - 1) % len(kinds)][0],
            "STARTEXECUTEDATE": sign + dt.timedelta(days=5),
            "ENDEXECUTEDATE": sign + dt.timedelta(days=185),
            "ORGANIZATIONCODE": "00001", "ISDELETED": False, "WFSTATUS": 1, "WFNAME": "已审批",
            **{k: D(v) for k, v in monthly.items()},
        }
        contracts.append(row)
        quality.append({
            "ID": f"DEMO-CQ-{i:03d}", "CREATIONTIME": sign, "CONTRACTID": cid,
            "NAME": "收到基低位发热量", "CODE": "QNETAR", "ITEMKIND": "煤质",
            "MINVALUE": D(4500 + RNG.randint(0, 300)), "MAXVALUE": D(5200 + RNG.randint(0, 400)),
            "ITEMUNIT": "Kcal/kg", "ORDERNUMBER": 1, "ORGANIZATIONCODE": "00001", "ISDELETED": False,
        })
        if i % 4 == 0:  # 四分之一合同再加一条硫分约束
            quality.append({
                "ID": f"DEMO-CQ-{i:03d}S", "CREATIONTIME": sign, "CONTRACTID": cid,
                "NAME": "干基全硫", "CODE": "STAD", "ITEMKIND": "煤质",
                "MINVALUE": D(0.2), "MAXVALUE": D(1.2), "ITEMUNIT": "%",
                "ORDERNUMBER": 2, "ORGANIZATIONCODE": "00001", "ISDELETED": False,
            })
    if template_id:
        for i in range(1, 301):
            temp_items.append({
                "ID": f"DEMO-TI-{i:03d}", "CREATIONTIME": dt.datetime(2026, 1, 1, 8, 0),
                "TEMPLATEID": template_id, "STANDARDVALUE": D(RNG.randint(4000, 6000)),
                "ORDERNUMBER": i % 12 + 1, "ITEMKIND": "量价条款",
                "LADDERCHECK": "是", "CLAUSE": f"第{i % 12 + 1}条 按热值区间结算",
                "ORGANIZATIONCODE": "00001", "ISDELETED": False,
            })
    await conn.rollback()  # 结束只读查询的 autobegin
    async with conn.begin():
        n1 = await _bulk(conn, "FUEL_CB_COALCONTRACT", contracts)
        n2 = await _bulk(conn, "FUEL_CB_COALCONTRACTQUALITY", quality)
        n3 = await _bulk(conn, "FUEL_CB_CONTRACTTEMPITEM", temp_items)
    print(f"[contract] 合同 {n1}、质量约束 {n2}、模板条款 {n3}")

    # ---------- 2. 采样 / 制样 / 明细 ----------
    samplings, sampling_detail, makes, make_detail = [], [], [], []
    for i in range(1, 241):
        sid = f"DEMO-SP-{i:03d}"
        batch = batches[(i - 1) % len(batches)]
        when = dt.datetime(2026, 6, 1) + dt.timedelta(hours=7 * i)
        samplings.append({
            "ID": sid, "CREATIONTIME": when, "ORGANIZATIONCODE": "00001", "ISDELETED": False,
            "INFACTORYBATCHID": batch[0], "SAMPLINGTYPE": "机械采样",
            "SAMPLECODE": f"CY2026{i:04d}", "SAMPLINGDATE": when,
            "ENDTIME": when + dt.timedelta(minutes=30), "SAMPLENUM": 1, "ISFINISH": 1,
            "SAMPLERNAME": "演示采样员", "SAMPLEUNITQTY": D(RNG.randint(20, 60)),
        })
        sampling_detail.append({
            "ID": f"DEMO-SPD-{i:03d}", "CREATIONTIME": when, "ISDELETED": False,
            "BARRELCODE": f"T{i:03d}", "SAMPLEWEIGHT": D(RNG.randint(18, 35)),
            "SAMPLINGID": sid, "SAMPLERNAME": "演示采样员",
            "BARRELINGTIME": when + dt.timedelta(minutes=20), "ORDERNUM": 1,
            "ORGANIZATIONCODE": "00001",
        })
        mid = f"DEMO-MK-{i:03d}"
        makes.append({
            "ID": mid, "CREATIONTIME": when, "ORGANIZATIONCODE": "00001", "ISDELETED": False,
            "MAKECODE": f"ZY2026{i:04d}", "MAKETYPE": "制样", "MAKEDATE": when,
            "SAMPLINGID": sid, "ISFINISH": 1, "FINISHTIME": when + dt.timedelta(hours=2),
        })
        for j, st in enumerate(("全水分样", "分析样", "存查样"), start=1):
            make_detail.append({
                "ID": f"DEMO-MKD-{i:03d}-{j}", "CREATIONTIME": when, "ISDELETED": False,
                "SAMPLECODE": f"ZY2026{i:04d}-{j}", "SAMPLETYPE": st,
                "SAMPLEWEIGHT": D(RNG.randint(50, 200)), "MAKEID": mid,
                "ORDERNUM": j, "CHECKWEIGHT": D(RNG.randint(45, 195)),
                "ORGANIZATIONCODE": "00001",
            })
    await conn.rollback()  # 结束只读查询的 autobegin
    async with conn.begin():
        a = await _bulk(conn, "FUEL_CMCS_RCSAMPLING", samplings)
        b = await _bulk(conn, "FUEL_CMCS_RCSAMPLINGDETAIL", sampling_detail)
        c = await _bulk(conn, "FUEL_CMCS_MAKE", makes)
        d = await _bulk(conn, "FUEL_CMCS_MAKEDETAIL", make_detail)
    print(f"[sample] 采样 {a}、采样明细 {b}、制样 {c}、制样明细 {d}")

    # ---------- 3. 细项化验（挂到现有化验单） ----------
    element, sulfur, heat, proximate, moisture = [], [], [], [], []
    for i, (aid, code, adate) in enumerate(assays, start=1):
        base = adate or dt.datetime(2026, 5, 1, 9, 0)
        element.append({
            "ID": f"DEMO-EL-{i:03d}", "CREATIONTIME": base, "ISDELETED": False,
            "SAMPLENUMBER": code, "PKID": aid, "ASSAYTIME": base, "ISEFFECTIVE": 1,
            "ORDERNUMBER": 1, "NAD": D(RNG.uniform(0.6, 1.2)), "HAD": D(RNG.uniform(3.5, 5.0)),
            "CAD": D(RNG.uniform(55, 70)), "ND": D(RNG.uniform(0.6, 1.2)),
            "CD": D(RNG.uniform(55, 70)), "HD": D(RNG.uniform(3.5, 5.0)),
            "MAD": D(RNG.uniform(5, 12)), "ORGANIZATIONCODE": "00001",
        })
        sulfur.append({
            "ID": f"DEMO-SF-{i:03d}", "CREATIONTIME": base, "ISDELETED": False,
            "SAMPLENUMBER": code, "PKID": aid, "ASSAYTIME": base, "ISEFFECTIVE": 1,
            "ORDERNUMBER": 1, "STAD": D(RNG.uniform(0.3, 1.6)), "ORGANIZATIONCODE": "00001",
        })
        heat.append({
            "ID": f"DEMO-HT-{i:03d}", "CREATIONTIME": base, "ISDELETED": False,
            "SAMPLENUMBER": code, "PKID": aid, "ASSAYTIME": base, "ISEFFECTIVE": 1,
            "ORDERNUMBER": 1, "QBAD": D(RNG.uniform(4000, 5600)),
            "CALCAPACITY": D(RNG.uniform(60, 76)), "ORGANIZATIONCODE": "00001",
        })
        proximate.append({
            "ID": f"DEMO-PX-{i:03d}", "CREATIONTIME": base, "ISDELETED": False,
            "SAMPLENUMBER": code, "PKID": aid, "ASSAYTIME": base, "ISEFFECTIVE": 1,
            "ORDERNUMBER": 1, "MAD": D(RNG.uniform(5, 12)), "VAD": D(RNG.uniform(25, 40)),
            "AAD": D(RNG.uniform(15, 30)), "ORGANIZATIONCODE": "00001",
        })
        moisture.append({
            "ID": f"DEMO-MS-{i:03d}", "CREATIONTIME": base, "ISDELETED": False,
            "SAMPLENUMBER": code, "PKID": aid, "ASSAYTIME": base, "ISEFFECTIVE": 1,
            "ORDERNUMBER": 1, "MAR": D(RNG.uniform(8, 20)), "WATERTYPE": "全水分",
            "DETERMINATION": "烘干法", "ORGANIZATIONCODE": "00001",
        })
    await conn.rollback()  # 结束只读查询的 autobegin
    async with conn.begin():
        e1 = await _bulk(conn, "FUEL_CMCS_ELEMENTASSAY", element)
        e2 = await _bulk(conn, "FUEL_CMCS_SULFURASSAY", sulfur)
        e3 = await _bulk(conn, "FUEL_CMCS_HEATASSAY", heat)
        e4 = await _bulk(conn, "FUEL_CMCS_PROXIMATEASSAY", proximate)
        e5 = await _bulk(conn, "FUEL_CMCS_MOISTUREASSAY", moisture)
    print(f"[assay] 元素 {e1}、硫 {e2}、热值 {e3}、工业分析 {e4}、水分 {e5}")

    # ---------- 4. 计划（年/月/日/采购） ----------
    py, pyd = [], []
    py.append({
        "ID": "DEMO-PY-2026", "CREATIONTIME": dt.datetime(2026, 1, 1), "ISDELETED": False,
        "ORGANIZATIONCODE": "00001", "YEAR": 2026, "INCOALQTY": D(1_200_000),
        "COALCOST": D(650_000_000), "COALSTOCK": D(300_000), "WFSTATUS": 1, "WFNAME": "已审批",
    })
    for m in range(1, 13):
        pyd.append({
            "ID": f"DEMO-PYD-{m:02d}", "CREATIONTIME": dt.datetime(2026, 1, 1), "ISDELETED": False,
            "ORGANIZATIONCODE": "00001", "MONTH": m, "INCOALQTY": D(100_000),
            "COALCOST": D(54_000_000), "COALSTOCK": D(25_000 + m * 800),
            "PLANYEARID": "DEMO-PY-2026",
        })
    pm, pmd = [], []
    for m in range(1, 13):
        mid = f"DEMO-PM-{m:02d}"
        pm.append({
            "ID": mid, "CREATIONTIME": dt.datetime(2026, m, 1), "ISDELETED": False,
            "ORGANIZATIONCODE": "00001", "PLANDATE": dt.datetime(2026, m, 1),
            "INCOALQTY": D(100_000), "PLANINCOALQTY": D(102_000),
            "COALCOST": D(54_000_000), "COALSTOCK": D(25_000 + m * 800),
            "PLANCOALSTOCK": D(26_000 + m * 800), "WFSTATUS": 1, "WFNAME": "已审批",
        })
        for j in range(3):
            pmd.append({
                "ID": f"DEMO-PMD-{m:02d}-{j + 1}", "CREATIONTIME": dt.datetime(2026, m, 1),
                "ISDELETED": False, "ORGANIZATIONCODE": "00001",
                "PLANMONTHID": mid, "MINEID": mines[j][0], "FUELKINDID": kinds[j % len(kinds)][0],
                "PLANPROCUREQTY": D(30_000 + j * 2_000), "QCAL": D(4800 + j * 100),
                "MT": D(12), "STAD": D(0.8), "VAD": D(30), "AAD": D(20), "ORDERNUMBER": j + 1,
            })
    pday, pdayd = [], []
    for d in range(1, 31):
        did = f"DEMO-PD-{d:02d}"
        pday.append({
            "ID": did, "CREATIONTIME": dt.datetime(2026, 10, d), "ISDELETED": False,
            "ORGANIZATIONCODE": "00001", "PLANDATE": dt.datetime(2026, 10, d),
            "ELECTRIC": D(9_000_000), "QCAL": D(4900), "COALCOST": D(1_800_000),
            "COALCOSTQTY": D(3_500), "INCOALQTY": D(3_300), "COALSTOCK": D(25_000 + d * 100),
        })
        for j in range(2):
            pdayd.append({
                "ID": f"DEMO-PDD-{d:02d}-{j + 1}", "CREATIONTIME": dt.datetime(2026, 10, d),
                "ISDELETED": False, "ORGANIZATIONCODE": "00001", "PLANDAYID": did,
                "MINEID": mines[j][0], "FUELKINDID": kinds[j % len(kinds)][0],
                "PLANPROCUREQTY": D(1_600 + j * 100), "QCAL": D(4900), "MT": D(12),
                "STAD": D(0.8), "VAD": D(30), "AAD": D(20), "ORDERNUMBER": j + 1,
            })
    pur, purd = [], []
    for m in range(1, 13):
        pid = f"DEMO-PU-{m:02d}"
        pur.append({
            "ID": pid, "CREATIONTIME": dt.datetime(2026, m, 1), "ORGANIZATIONCODE": "00001",
            "PURCHASEDATE": dt.datetime(2026, m, 1), "DEMANDQTY": D(100_000),
            "PURCHASEQTY": D(102_000), "STARTSTOCKSQTY": D(25_000 + m * 800),
            "ENDSTOCKSQTY": D(27_000 + m * 800), "INFURNACEQCAL": D(4900),
            "INFACSTANDARDPRICE": D(560),
        })
        for j in range(5):
            purd.append({
                "ID": f"DEMO-PUD-{m:02d}-{j + 1}", "CREATIONTIME": dt.datetime(2026, m, 1),
                "PURCHASEMONTHID": pid, "CMCSSUPPLIERID": suppliers[j][0],
                "SORT": j + 1, "PLANQTY": D(20_000), "KCAL": D(4800 + j * 80),
                "S": D(0.8), "V": D(30), "PRICE": D(540 + j * 6),
                "FREIGHTPRICE": D(35), "STANDARDPRICE": D(505), "HUNDREDKCALPRICE": D(110),
            })
    await conn.rollback()  # 结束只读查询的 autobegin
    async with conn.begin():
        p1 = await _bulk(conn, "FUEL_CMCS_PLANYEAR", py)
        p2 = await _bulk(conn, "FUEL_CMCS_PLANYEARDETAIL", pyd)
        p3 = await _bulk(conn, "FUEL_CMCS_PLANMONTH", pm)
        p4 = await _bulk(conn, "FUEL_CMCS_PLANMONTHDETAIL", pmd)
        p5 = await _bulk(conn, "FUEL_CMCS_PLANDAY", pday)
        p6 = await _bulk(conn, "FUEL_CMCS_PLANDAYDETAIL", pdayd)
        p7 = await _bulk(conn, "FUEL_CMCS_PURCHASEMONTH", pur)
        p8 = await _bulk(conn, "FUEL_CMCS_PURCHASEMONTHDETAIL", purd)
    print(f"[plan] 年 {p1}/{p2}、月 {p3}/{p4}、日 {p5}/{p6}、采购 {p7}/{p8}")

    # ---------- 5. 组态 / 人脸 / 小程序 ----------
    classes, canvas_classes, canvases, components, refs = [], [], [], [], []
    for i in range(1, 7):
        classes.append({
            "ID": f"DEMO-CC-{i:02d}", "CREATIONTIME": dt.datetime(2026, 3, 1), "ISDELETED": False,
            "TENANTID": 0, "NAME": f"演示组件分类{i}", "DESCRIPTION": "演示数据",
            "TREECODE": f"{i:02d}", "SORT": i,
        })
    for i in range(1, 7):
        canvas_classes.append({
            "ID": f"DEMO-CVCL-{i:02d}", "CREATIONTIME": dt.datetime(2026, 3, 1), "ISDELETED": False,
            "ORGANIZATIONCODE": "00001", "ORGANIZATIONID": 1,
            "NAME": f"演示画面分类{i}", "DESCRIPTION": "演示数据",
            "TREECODE": f"{i:02d}", "SORT": i,
        })
    for i in range(1, 13):
        canvases.append({
            "ID": f"DEMO-CV-{i:02d}", "CREATIONTIME": dt.datetime(2026, 3, 2), "ISDELETED": False,
            "TENANTID": 0, "ORGANIZATIONCODE": "00001", "ORGANIZATIONID": 1,
            "CLASSIFICATIONID": f"DEMO-CVCL-{(i - 1) % 6 + 1:02d}",
            "NAME": f"演示组态画面{i}", "DESCRIPTION": "演示数据", "SORTS": i,
            "CONTENT": "{}",
        })
    for i in range(1, 41):
        components.append({
            "ID": f"DEMO-CP-{i:03d}", "CREATIONTIME": dt.datetime(2026, 3, 3), "ISDELETED": False,
            "TENANTID": 0, "CLASSIFICATIONID": f"DEMO-CC-{(i - 1) % 6 + 1:02d}",
            "NAME": f"演示组件{i}", "CONTENT": "{}", "SORT": i,
            "ISDEFAULT": False, "TYPE": 1,
        })
    for i in range(1, 121):
        refs.append({
            "ID": f"DEMO-CVC-{i:03d}",
            "CANVASID": f"DEMO-CV-{(i - 1) % 12 + 1:02d}",
            "COMPONENTID": f"DEMO-CP-{(i - 1) % 40 + 1:03d}",
            "KEY": f"k{i}", "INSTANCENAME": f"实例{i}",
        })
    personnel = []
    for i in range(1, 21):
        personnel.append({
            "ID": f"DEMO-FR-{i:02d}", "CREATIONTIME": dt.datetime(2026, 4, 1), "ISDELETED": False,
            "NAME": f"演示人员{i:02d}", "SEX": "男" if i % 2 else "女",
            "IDTYPE": "身份证", "IDNUMBER": f"11010119900101{i:04d}",
            "PHONENUMBER": f"1380000{i:04d}", "CLIENTTYPE": "企业微信",
            "CLIENTID": f"wx_demo_{i:02d}", "AUDITRESULT": 1,
        })
    apps = []
    for i in range(1, 7):
        apps.append({
            "ID": f"DEMO-APP-{i:02d}", "CREATIONTIME": dt.datetime(2026, 5, 1), "ISDELETED": False,
            "ORGANIZATIONCODE": "00001", "APPNAME": "AIStation 移动端",
            "APPTYPE": "Android" if i % 2 else "iOS",
            "VERSIONNUMBER": f"2.{i}.0",
            "RELEASETIME": (dt.datetime(2026, 5, 1) + dt.timedelta(days=i * 9) if i <= 4 else None),
            "REMARK": "演示数据",
        })
    await conn.rollback()  # 结束只读查询的 autobegin
    async with conn.begin():
        c0 = await _bulk(conn, "CMMS_CANVASCLASSIFICATION", canvas_classes)
        c1 = await _bulk(conn, "CMMS_COMPONENTCLASSIFICATION", classes)
        c2 = await _bulk(conn, "CMMS_CANVAS", canvases)
        c3 = await _bulk(conn, "CMMS_COMPONENT", components)
        c4 = await _bulk(conn, "CMMS_CANVASCOMPONENT", refs)
        c5 = await _bulk(conn, "FR_PERSONNELINFO", personnel)
        c6 = await _bulk(conn, "CMCS_APPVERSION", apps)
    print(f"[other] 画面分类 {c0}、组件分类 {c1}、画面 {c2}、组件 {c3}、引用 {c4}、人员 {c5}、版本 {c6}")


async def verify(conn) -> None:
    from sqlalchemy import text

    checks = [
        ("合同", 'SELECT count(*), sum("CONTRACTAMOUNT") FROM "FUEL_CB_COALCONTRACT"'),
        ("合同质量约束", 'SELECT count(*) FROM "FUEL_CB_COALCONTRACTQUALITY"'),
        ("模板条款", 'SELECT count(*) FROM "FUEL_CB_CONTRACTTEMPITEM"'),
        ("采样", 'SELECT count(*) FROM "FUEL_CMCS_RCSAMPLING"'),
        ("采样明细", 'SELECT count(*) FROM "FUEL_CMCS_RCSAMPLINGDETAIL"'),
        ("制样", 'SELECT count(*) FROM "FUEL_CMCS_MAKE"'),
        ("制样明细", 'SELECT count(*) FROM "FUEL_CMCS_MAKEDETAIL"'),
        ("元素", 'SELECT count(*), round(avg("CAD"),2) FROM "FUEL_CMCS_ELEMENTASSAY"'),
        ("硫", 'SELECT count(*), round(avg("STAD"),3) FROM "FUEL_CMCS_SULFURASSAY"'),
        ("热值", 'SELECT count(*), round(avg("QBAD"),2) FROM "FUEL_CMCS_HEATASSAY"'),
        ("工业分析", 'SELECT count(*) FROM "FUEL_CMCS_PROXIMATEASSAY"'),
        ("水分", 'SELECT count(*) FROM "FUEL_CMCS_MOISTUREASSAY"'),
        ("年计划", 'SELECT count(*) FROM "FUEL_CMCS_PLANYEAR"'),
        ("月计划", 'SELECT count(*) FROM "FUEL_CMCS_PLANMONTH"'),
        ("日计划", 'SELECT count(*) FROM "FUEL_CMCS_PLANDAY"'),
        ("采购计划", 'SELECT count(*) FROM "FUEL_CMCS_PURCHASEMONTH"'),
        ("组态画面", 'SELECT count(*) FROM "CMMS_CANVAS"'),
        ("组态画面分类", 'SELECT count(*) FROM "CMMS_CANVASCLASSIFICATION"'),
        ("组件", 'SELECT count(*) FROM "CMMS_COMPONENT"'),
        ("画面引用组件", 'SELECT count(*) FROM "CMMS_CANVASCOMPONENT"'),
        ("人员", 'SELECT count(*) FROM "FR_PERSONNELINFO"'),
        ("小程序版本", 'SELECT count(*) FROM "CMCS_APPVERSION"'),
    ]
    for label, sql in checks:
        print(f"[verify] {label}: {(await conn.execute(text(sql))).fetchone()}")


async def main() -> None:
    from main import create_app

    create_app()
    engine, ds_id = await _engine()
    await clone_query_meta(ds_id)
    await seed_extra_metrics(ds_id)
    async with engine.connect() as conn:
        await seed_business(conn)
        await verify(conn)


if __name__ == "__main__":
    asyncio.run(main())
