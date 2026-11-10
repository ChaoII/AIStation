"""ds:6（本地副本）真实业务数据重建：按今天锚定的完整链路。

链路：合同 → 入厂批次 → 采样 → 制样 → 化验（细项） → 结算（主/明细） → 计划/存煤。

- 时间锚定 `date.today()`：合同覆盖近 12 个月签约、执行期 6 个月；批次覆盖最近 90 天；
  采样/制样/化验跟随批次；结算覆盖近 12 个月；计划为当年 12 个月 + 最近 30 天。
- 主外键：合同↔供应商/矿点/煤种；批次↔合同（供应商 + 到厂日期落在执行期）；
  采样→批次、制样→采样、化验→批次/制样、细项化验→化验单、结算主→明细、计划主→明细。
- 幂等：先删 `DEMO-` 前缀的旧演示行，再重建。
- 只写 ds:6，不动 ds:4（评测基准不变）。

用法：
    cd backend
    uv run python scripts/seed_realistic_business_data.py
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import random
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DS_CODE = "ezdcs_local"
TODAY = dt.datetime.combine(dt.date.today(), dt.time())
RNG = random.Random(20261111)
ORG = "00001"


def D(v: float) -> Decimal:
    return Decimal(str(round(v, 2)))


def ts(day, hour: int = 8, minute: int = 0) -> dt.datetime:
    if isinstance(day, dt.datetime):
        return day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return dt.datetime.combine(day, dt.time(hour, minute))


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


# 所有可能残留 DEMO 行的表（子表在前）
DEMO_TABLES = [
    "FUEL_CMCS_PURCHASEMONTHDETAIL", "FUEL_CMCS_PURCHASEMONTH",
    "FUEL_CMCS_PLANMONTHDETAIL", "FUEL_CMCS_PLANMONTH",
    "FUEL_CMCS_PLANDAYDETAIL", "FUEL_CMCS_PLANDAY",
    "FUEL_CMCS_PLANYEARDETAIL", "FUEL_CMCS_PLANYEAR",
    "FUEL_CB_COALBALANCEDETAIL", "FUEL_CB_COALBALANCE",
    "FUEL_CMCS_MAKEDETAIL", "FUEL_CMCS_MAKE",
    "FUEL_CMCS_RCSAMPLINGDETAIL", "FUEL_CMCS_RCSAMPLING",
    "FUEL_CMCS_ELEMENTASSAY", "FUEL_CMCS_SULFURASSAY", "FUEL_CMCS_HEATASSAY",
    "FUEL_CMCS_PROXIMATEASSAY", "FUEL_CMCS_MOISTUREASSAY", "FUEL_CMCS_ASSAY",
    "FUEL_CB_CONTRACTTEMPITEM", "FUEL_CB_COALCONTRACTQUALITY", "FUEL_CB_COALCONTRACT",
    "CMMS_CANVASCOMPONENT", "CMMS_COMPONENT", "CMMS_CANVAS",
    "CMMS_CANVASCLASSIFICATION", "CMMS_COMPONENTCLASSIFICATION",
    "FR_PERSONNELINFO", "CMCS_APPVERSION", "FUEL_CMCS_INFACTORYBATCH",
]


async def reset(conn) -> None:
    from sqlalchemy import text

    await conn.execute(text(
        'UPDATE "FUEL_CMCS_INFACTORYBATCH" SET "CONTRACTID"=NULL WHERE "CONTRACTID" LIKE \'DEMO-%\''
    ))
    for t in DEMO_TABLES:
        await conn.execute(text(f'DELETE FROM "{t}" WHERE "ID" LIKE \'DEMO-%\''))
    # 源库脏日期：1900-01-01 → NULL（不参与时间统计）
    await conn.execute(text(
        'UPDATE "FUEL_CMCS_INFACTORYBATCH" SET "FACTARRIVEDATE"=NULL WHERE "FACTARRIVEDATE" < \'2000-01-01\''
    ))
    await conn.commit()


async def refs(conn):
    from sqlalchemy import text

    suppliers = (await conn.execute(text(
        'SELECT "ID","NAME" FROM "FUEL_CMCS_SUPPLIER" WHERE "ISDELETED"=false ORDER BY "ID"'
    ))).fetchall()
    mines = (await conn.execute(text(
        'SELECT "ID","NAME" FROM "FUEL_CMCS_MINE" WHERE "ISDELETED"=false ORDER BY "ID"'
    ))).fetchall()
    kinds = (await conn.execute(text(
        'SELECT "ID","NAME" FROM "FUEL_CMCS_FUELKIND" WHERE "ISDELETED"=false ORDER BY "ID"'
    ))).fetchall()
    template_id = (await conn.execute(text(
        'SELECT "ID" FROM "FUEL_CB_CONTRACTTEMPLANTE" WHERE "ISDELETED"=false ORDER BY "ID" LIMIT 1'
    ))).scalar()
    return suppliers, mines, kinds, template_id


def split_months(total: int, start: dt.date, months: int = 6) -> dict[str, int]:
    """把数量均分到执行期覆盖的自然月（12 个月列），余数落最后一个月。"""
    keys = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
            "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]
    out = dict.fromkeys(keys, 0)
    base = total // months
    seq = []
    y, m = start.year, start.month
    for _ in range(months):
        seq.append(keys[m - 1])
        m += 1
        if m > 12:
            m = 1
            y += 1
    for k in seq:
        out[k] += base
    out[seq[-1]] += total - base * months
    return out


async def seed(conn) -> None:
    from sqlalchemy import text

    suppliers, mines, kinds, template_id = await refs(conn)
    print(f"[ref] suppliers={len(suppliers)} mines={len(mines)} kinds={len(kinds)}")
    await reset(conn)

    # ---------- 1. 合同（120 份，近 12 个月签约，执行 6 个月） ----------
    contracts = []
    quality = []
    contract_meta = []  # (id, supplier_id, start, end, price)
    for i in range(1, 121):
        sid, sname = suppliers[(i - 1) % min(len(suppliers), 15)]
        mine_id, mine_name = mines[(i - 1) % min(len(mines), 20)]
        kind_id, kind_name = kinds[(i - 1) % len(kinds)]
        sign = TODAY - dt.timedelta(days=360) + dt.timedelta(days=(i - 1) * 3)
        start = sign + dt.timedelta(days=3)
        end = start + dt.timedelta(days=180)
        amount = RNG.randint(20000, 80000)
        price = RNG.randint(480, 620)
        cid = f"DEMO-CT-{i:03d}"
        monthly = split_months(amount, start, 6)
        contracts.append({
            "ID": cid, "CREATIONTIME": ts(sign), "SIGNDATE": ts(sign),
            "CONTRACTNUM": f"HT{sign.year}{i:04d}", "CONTRACTTYPE": "长协煤" if i % 2 else "市场煤",
            "CONTRACTAMOUNT": D(amount), "CONTRACTPRICE": D(price),
            "CONTRACTFREIGHT": D(RNG.randint(20, 60)), "PETTYPRICE": D(RNG.randint(5, 15)),
            "SUPPLIERID": sid, "MINENAMES": mine_name, "MINEIDS": mine_id,
            "FUELKINDNAMES": kind_name, "FUELKINDIDS": kind_id,
            "STARTEXECUTEDATE": ts(start), "ENDEXECUTEDATE": ts(end),
            "ORGANIZATIONCODE": ORG, "ISDELETED": False, "WFSTATUS": 1, "WFNAME": "已审批",
            **{k: D(v) for k, v in monthly.items()},
        })
        contract_meta.append((cid, sid, start, end, price))
        quality.append({
            "ID": f"DEMO-CQ-{i:03d}", "CREATIONTIME": ts(sign), "CONTRACTID": cid,
            "NAME": "收到基低位发热量", "CODE": "QNETAR", "ITEMKIND": "煤质",
            "MINVALUE": D(4500 + RNG.randint(0, 300)), "MAXVALUE": D(5200 + RNG.randint(0, 400)),
            "ITEMUNIT": "Kcal/kg", "ORDERNUMBER": 1, "ORGANIZATIONCODE": ORG, "ISDELETED": False,
        })
        if i % 4 == 0:
            quality.append({
                "ID": f"DEMO-CQ-{i:03d}S", "CREATIONTIME": ts(sign), "CONTRACTID": cid,
                "NAME": "干基全硫", "CODE": "STAD", "ITEMKIND": "煤质",
                "MINVALUE": D(0.2), "MAXVALUE": D(1.2), "ITEMUNIT": "%",
                "ORDERNUMBER": 2, "ORGANIZATIONCODE": ORG, "ISDELETED": False,
            })
    temp_items = []
    if template_id:
        for i in range(1, 301):
            temp_items.append({
                "ID": f"DEMO-TI-{i:03d}", "CREATIONTIME": ts(TODAY - dt.timedelta(days=300)),
                "TEMPLATEID": template_id, "STANDARDVALUE": D(RNG.randint(4000, 6000)),
                "ORDERNUMBER": i % 12 + 1, "ITEMKIND": "量价条款",
                "LADDERCHECK": "是", "CLAUSE": f"第{i % 12 + 1}条 按热值区间结算",
                "ORGANIZATIONCODE": ORG, "ISDELETED": False,
            })
    await conn.rollback()
    async with conn.begin():
        n1 = await _bulk(conn, "FUEL_CB_COALCONTRACT", contracts)
        n2 = await _bulk(conn, "FUEL_CB_COALCONTRACTQUALITY", quality)
        n3 = await _bulk(conn, "FUEL_CB_CONTRACTTEMPITEM", temp_items)
    print(f"[contract] 合同 {n1}、质量约束 {n2}、模板条款 {n3}")

    # ---------- 2. 批次（300 条，最近 90 天） ----------
    batches = []
    batch_meta = []  # (batch_id, supplier_id, date)
    for i in range(1, 301):
        on = TODAY - dt.timedelta(days=89) + dt.timedelta(hours=i * 7)
        sid, sname = suppliers[(i - 1) % min(len(suppliers), 15)]
        mine_id, mine_name = mines[(i - 1) % min(len(mines), 20)]
        kind_id, kind_name = kinds[(i - 1) % len(kinds)]
        check = RNG.randint(2000, 5000)
        bid = f"DEMO-B-{i:03d}"
        batches.append({
            "ID": bid, "CREATIONTIME": on, "BATCH": f"HC{on:%Y%m%d}-{i:03d}",
            "SUPPLIERID": sid, "SUPPLIERNAME": sname, "MINEID": mine_id, "MINENAME": mine_name,
            "FUELKINDID": kind_id, "FUELKINDNAME": kind_name,
            "FACTARRIVEDATE": on, "TICKETQTY": D(check + RNG.randint(50, 200)),
            "GROSSQTY": D(check + 1200), "SKINQTY": D(1200), "SUTTLEQTY": D(check + 60),
            "CHECKQTY": D(check), "ESTIMATEKCAL": D(RNG.randint(4500, 5200)),
            "TRANSPORTNUMBER": 1, "ORGANIZATIONCODE": ORG, "ISDELETED": False,
        })
        batch_meta.append((bid, sid, on.date()))
    await conn.rollback()
    async with conn.begin():
        nb = await _bulk(conn, "FUEL_CMCS_INFACTORYBATCH", batches)
    print(f"[batch] 新增 {nb} 条（最近 90 天）")

    # 批次 → 合同（供应商 + 到厂日期在执行期）
    await conn.rollback()
    async with conn.begin():
        linked = await conn.execute(text(
            'UPDATE "FUEL_CMCS_INFACTORYBATCH" b SET "CONTRACTID" = ('
            'SELECT c."ID" FROM "FUEL_CB_COALCONTRACT" c '
            "WHERE c.\"ID\" LIKE 'DEMO-%' AND c.\"SUPPLIERID\"=b.\"SUPPLIERID\" "
            'AND b."FACTARRIVEDATE" BETWEEN c."STARTEXECUTEDATE" AND c."ENDEXECUTEDATE" '
            'ORDER BY c."STARTEXECUTEDATE" DESC LIMIT 1) '
            'WHERE b."ID" LIKE \'DEMO-B-%\''
        ))
    print(f"[batch] 合同回填 {linked.rowcount} 条")

    # ---------- 3. 采样 / 制样 / 化验（跟随批次） ----------
    sampling, sdetail, makes, mdetail, assays = [], [], [], [], []
    for i, (bid, _sid, day) in enumerate(batch_meta, start=1):
        when = ts(day, 9, 30) + dt.timedelta(minutes=i % 45)
        spid = f"DEMO-SP-{i:03d}"
        sampling.append({
            "ID": spid, "CREATIONTIME": when, "ORGANIZATIONCODE": ORG, "ISDELETED": False,
            "INFACTORYBATCHID": bid, "SAMPLINGTYPE": "机械采样",
            "SAMPLECODE": f"CY{day:%Y%m%d}{i:03d}", "SAMPLINGDATE": when,
            "ENDTIME": when + dt.timedelta(minutes=30), "SAMPLENUM": 1, "ISFINISH": 1,
            "SAMPLERNAME": "演示采样员", "SAMPLEUNITQTY": D(RNG.randint(20, 60)),
        })
        sdetail.append({
            "ID": f"DEMO-SPD-{i:03d}", "CREATIONTIME": when, "ISDELETED": False,
            "BARRELCODE": f"T{i:03d}", "SAMPLEWEIGHT": D(RNG.randint(18, 35)),
            "SAMPLINGID": spid, "SAMPLERNAME": "演示采样员",
            "BARRELINGTIME": when + dt.timedelta(minutes=20), "ORDERNUM": 1,
            "ORGANIZATIONCODE": ORG,
        })
        mwhen = when + dt.timedelta(hours=3)
        mkid = f"DEMO-MK-{i:03d}"
        makes.append({
            "ID": mkid, "CREATIONTIME": mwhen, "ORGANIZATIONCODE": ORG, "ISDELETED": False,
            "MAKECODE": f"ZY{day:%Y%m%d}{i:03d}", "MAKETYPE": "制样", "MAKEDATE": mwhen,
            "SAMPLINGID": spid, "ISFINISH": 1, "FINISHTIME": mwhen + dt.timedelta(hours=2),
        })
        for j, st in enumerate(("全水分样", "分析样", "存查样"), start=1):
            mdetail.append({
                "ID": f"DEMO-MKD-{i:03d}-{j}", "CREATIONTIME": mwhen, "ISDELETED": False,
                "SAMPLECODE": f"ZY{day:%Y%m%d}{i:03d}-{j}", "SAMPLETYPE": st,
                "SAMPLEWEIGHT": D(RNG.randint(50, 200)), "MAKEID": mkid,
                "ORDERNUM": j, "CHECKWEIGHT": D(RNG.randint(45, 195)),
                "ORGANIZATIONCODE": ORG,
            })
        assays.append({
            "ID": f"DEMO-AS-{i:03d}", "CREATIONTIME": mwhen + dt.timedelta(hours=20),
            "ASSAYDATE": mwhen + dt.timedelta(hours=20), "INFACTORYBATCHID": bid,
            "MAKEID": mkid, "DISCRIMINATOR": "Rc", "ISASSAY": 99, "ISFINISH": 1,
            "ASSAYCODE": f"HY{day:%Y%m%d}{i:03d}", "ORGANIZATIONCODE": ORG, "ISDELETED": False,
        })
    await conn.rollback()
    async with conn.begin():
        a = await _bulk(conn, "FUEL_CMCS_RCSAMPLING", sampling)
        b = await _bulk(conn, "FUEL_CMCS_RCSAMPLINGDETAIL", sdetail)
        c = await _bulk(conn, "FUEL_CMCS_MAKE", makes)
        d = await _bulk(conn, "FUEL_CMCS_MAKEDETAIL", mdetail)
        e = await _bulk(conn, "FUEL_CMCS_ASSAY", assays)
    print(f"[chain] 采样 {a}、采样明细 {b}、制样 {c}、制样明细 {d}、化验单 {e}")

    # 细项化验：覆盖全部化验单（原有 + 新增）
    all_assays = (await conn.execute(text(
        'SELECT "ID","ASSAYCODE","ASSAYDATE" FROM "FUEL_CMCS_ASSAY" '
        'WHERE "ISDELETED"=false ORDER BY "ASSAYDATE"'
    ))).fetchall()
    element, sulfur, heat, proximate, moisture = [], [], [], [], []
    for i, (aid, code, adate) in enumerate(all_assays, start=1):
        base = adate or ts(TODAY - dt.timedelta(days=30))
        element.append({
            "ID": f"DEMO-EL-{i:04d}", "CREATIONTIME": base, "ISDELETED": False,
            "SAMPLENUMBER": code, "PKID": aid, "ASSAYTIME": base, "ISEFFECTIVE": 1,
            "ORDERNUMBER": 1, "NAD": D(RNG.uniform(0.6, 1.2)), "HAD": D(RNG.uniform(3.5, 5.0)),
            "CAD": D(RNG.uniform(55, 70)), "ND": D(RNG.uniform(0.6, 1.2)),
            "CD": D(RNG.uniform(55, 70)), "HD": D(RNG.uniform(3.5, 5.0)),
            "MAD": D(RNG.uniform(5, 12)), "ORGANIZATIONCODE": ORG,
        })
        sulfur.append({
            "ID": f"DEMO-SF-{i:04d}", "CREATIONTIME": base, "ISDELETED": False,
            "SAMPLENUMBER": code, "PKID": aid, "ASSAYTIME": base, "ISEFFECTIVE": 1,
            "ORDERNUMBER": 1, "STAD": D(RNG.uniform(0.3, 1.6)), "ORGANIZATIONCODE": ORG,
        })
        heat.append({
            "ID": f"DEMO-HT-{i:04d}", "CREATIONTIME": base, "ISDELETED": False,
            "SAMPLENUMBER": code, "PKID": aid, "ASSAYTIME": base, "ISEFFECTIVE": 1,
            "ORDERNUMBER": 1, "QBAD": D(RNG.uniform(4000, 5600)),
            "CALCAPACITY": D(RNG.uniform(60, 76)), "ORGANIZATIONCODE": ORG,
        })
        proximate.append({
            "ID": f"DEMO-PX-{i:04d}", "CREATIONTIME": base, "ISDELETED": False,
            "SAMPLENUMBER": code, "PKID": aid, "ASSAYTIME": base, "ISEFFECTIVE": 1,
            "ORDERNUMBER": 1, "MAD": D(RNG.uniform(5, 12)), "VAD": D(RNG.uniform(25, 40)),
            "AAD": D(RNG.uniform(15, 30)), "ORGANIZATIONCODE": ORG,
        })
        moisture.append({
            "ID": f"DEMO-MS-{i:04d}", "CREATIONTIME": base, "ISDELETED": False,
            "SAMPLENUMBER": code, "PKID": aid, "ASSAYTIME": base, "ISEFFECTIVE": 1,
            "ORDERNUMBER": 1, "MAR": D(RNG.uniform(8, 20)), "WATERTYPE": "全水分",
            "DETERMINATION": "烘干法", "ORGANIZATIONCODE": ORG,
        })
    await conn.rollback()
    async with conn.begin():
        e1 = await _bulk(conn, "FUEL_CMCS_ELEMENTASSAY", element)
        e2 = await _bulk(conn, "FUEL_CMCS_SULFURASSAY", sulfur)
        e3 = await _bulk(conn, "FUEL_CMCS_HEATASSAY", heat)
        e4 = await _bulk(conn, "FUEL_CMCS_PROXIMATEASSAY", proximate)
        e5 = await _bulk(conn, "FUEL_CMCS_MOISTUREASSAY", moisture)
    print(f"[assay] 覆盖 {len(all_assays)} 张化验单（元素 {e1}/硫 {e2}/热值 {e3}/工业分析 {e4}/水分 {e5}）")

    # ---------- 4. 结算（近 12 个月，3 条/月，主+明细） ----------
    bal, bald = [], []

    def month_day(offset: int) -> dt.datetime:
        y, mo = TODAY.year, TODAY.month - offset
        while mo <= 0:
            mo += 12
            y -= 1
        return ts(dt.date(y, mo, 5), 10)

    for m in range(12):
        bal_day = month_day(m)  # 从当月开始往前推 12 个月（含本月）
        for j in range(3):
            sid, sname = suppliers[(m * 3 + j) % min(len(suppliers), 15)]
            cands = [c for c in contract_meta if c[1] == sid and c[2] <= bal_day <= c[3]]
            cid = cands[-1][0] if cands else ""
            price = cands[-1][4] if cands else RNG.randint(480, 620)
            qty = RNG.randint(800, 2000)
            bid = f"DEMO-BAL2-{m:02d}-{j + 1}"
            bal.append({
                "ID": bid, "CREATIONTIME": bal_day, "BALANCEDATE": bal_day,
                "CONTRACTID": cid, "SUPPLIERID": sid, "BALANCEQTY": D(qty),
                "CONTRACTPRICE": D(price), "COALPRICE": D(price + 15),
                "COALMONEY": D(qty * (price + 15)), "CHECKQTY": D(qty + 5),
                "MARGINQTY": D(-5), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
                "WFSTATUS": 1, "WFNAME": "已审批", "BALANCENUM": f"JS{bal_day:%Y%m}{j + 1}",
            })
            bald.append({
                "ID": f"DEMO-BALD2-{m:02d}-{j + 1}", "CREATIONTIME": bal_day,
                "BALANCEID": bid, "BALANCEQTY": D(qty), "CONTRACTPRICE": D(price),
                "COALPRICE": D(price + 15), "RAILLOST": D(RNG.randint(3, 10)),
                "BALANCEREDUCEQTY": D(RNG.randint(1, 6)), "CHECKQTY": D(qty + 5),
                "ORGANIZATIONCODE": ORG, "ISDELETED": False, "ORDERNUMBER": 1,
            })
    await conn.rollback()
    async with conn.begin():
        b1 = await _bulk(conn, "FUEL_CB_COALBALANCE", bal)
        b2 = await _bulk(conn, "FUEL_CB_COALBALANCEDETAIL", bald)
    print(f"[settlement] 结算 {b1}、明细 {b2}（近 12 个月）")

    # ---------- 5. 计划（2026 年 12 个月 + 最近 30 天） ----------
    py = [{
        "ID": f"DEMO-PY-{TODAY.year}", "CREATIONTIME": ts(dt.date(TODAY.year, 1, 1)),
        "ISDELETED": False, "ORGANIZATIONCODE": ORG, "YEAR": TODAY.year,
        "INCOALQTY": D(1_200_000), "COALCOST": D(650_000_000), "COALSTOCK": D(300_000),
        "WFSTATUS": 1, "WFNAME": "已审批",
    }]
    pyd = [{
        "ID": f"DEMO-PYD-{m:02d}", "CREATIONTIME": ts(dt.date(TODAY.year, 1, 1)),
        "ISDELETED": False, "ORGANIZATIONCODE": ORG, "MONTH": m,
        "INCOALQTY": D(100_000), "COALCOST": D(54_000_000), "COALSTOCK": D(25_000 + m * 800),
        "PLANYEARID": f"DEMO-PY-{TODAY.year}",
    } for m in range(1, 13)]
    pm, pmd = [], []
    for m in range(1, 13):
        mid = f"DEMO-PM-{m:02d}"
        pm.append({
            "ID": mid, "CREATIONTIME": ts(dt.date(TODAY.year, m, 1)), "ISDELETED": False,
            "ORGANIZATIONCODE": ORG, "PLANDATE": ts(dt.date(TODAY.year, m, 1)),
            "INCOALQTY": D(100_000), "PLANINCOALQTY": D(102_000),
            "COALCOST": D(54_000_000), "COALSTOCK": D(25_000 + m * 800),
            "PLANCOALSTOCK": D(26_000 + m * 800), "WFSTATUS": 1, "WFNAME": "已审批",
        })
        for j in range(8):
            pmd.append({
                "ID": f"DEMO-PMD-{m:02d}-{j + 1}", "CREATIONTIME": ts(dt.date(TODAY.year, m, 1)),
                "ISDELETED": False, "ORGANIZATIONCODE": ORG, "PLANMONTHID": mid,
                "MINEID": mines[j % len(mines)][0], "FUELKINDID": kinds[j % len(kinds)][0],
                "PLANPROCUREQTY": D(12_500 + j * 300), "QCAL": D(4800 + j * 40),
                "MT": D(12), "STAD": D(0.8), "VAD": D(30), "AAD": D(20), "ORDERNUMBER": j + 1,
            })
    pday, pdayd = [], []
    for d in range(30):
        day = TODAY - dt.timedelta(days=29 - d)
        did = f"DEMO-PD-{day:%m%d}"
        pday.append({
            "ID": did, "CREATIONTIME": ts(day), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
            "PLANDATE": ts(day), "ELECTRIC": D(9_000_000), "QCAL": D(4900),
            "COALCOST": D(1_800_000), "COALCOSTQTY": D(3_500), "INCOALQTY": D(3_300),
            "COALSTOCK": D(25_000 + d * 100),
        })
        for j in range(3):
            pdayd.append({
                "ID": f"DEMO-PDD-{day:%m%d}-{j + 1}", "CREATIONTIME": ts(day), "ISDELETED": False,
                "ORGANIZATIONCODE": ORG, "PLANDAYID": did, "MINEID": mines[j][0],
                "FUELKINDID": kinds[j % len(kinds)][0], "PLANPROCUREQTY": D(1_100 + j * 50),
                "QCAL": D(4900), "MT": D(12), "STAD": D(0.8), "VAD": D(30), "AAD": D(20),
                "ORDERNUMBER": j + 1,
            })
    pur, purd = [], []
    for m in range(1, 13):
        pid = f"DEMO-PU-{m:02d}"
        pur.append({
            "ID": pid, "CREATIONTIME": ts(dt.date(TODAY.year, m, 1)), "ORGANIZATIONCODE": ORG,
            "PURCHASEDATE": ts(dt.date(TODAY.year, m, 1)), "DEMANDQTY": D(100_000),
            "PURCHASEQTY": D(102_000), "STARTSTOCKSQTY": D(25_000 + m * 800),
            "ENDSTOCKSQTY": D(27_000 + m * 800), "INFURNACEQCAL": D(4900),
            "INFACSTANDARDPRICE": D(560),
        })
        for j in range(8):
            purd.append({
                "ID": f"DEMO-PUD-{m:02d}-{j + 1}", "CREATIONTIME": ts(dt.date(TODAY.year, m, 1)),
                "PURCHASEMONTHID": pid, "CMCSSUPPLIERID": suppliers[j % len(suppliers)][0],
                "SORT": j + 1, "PLANQTY": D(12_500), "KCAL": D(4800 + j * 40),
                "S": D(0.8), "V": D(30), "PRICE": D(540 + j * 4),
                "FREIGHTPRICE": D(35), "STANDARDPRICE": D(505), "HUNDREDKCALPRICE": D(110),
            })
    await conn.rollback()
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

    # ---------- 6. 组态 / 人脸 / 小程序 ----------
    cclasses = [{
        "ID": f"DEMO-CC-{i:02d}", "CREATIONTIME": ts(TODAY - dt.timedelta(days=240)), "ISDELETED": False,
        "TENANTID": 0, "NAME": f"演示组件分类{i}", "DESCRIPTION": "演示数据",
        "TREECODE": f"{i:02d}", "SORT": i,
    } for i in range(1, 7)]
    vclasses = [{
        "ID": f"DEMO-CVCL-{i:02d}", "CREATIONTIME": ts(TODAY - dt.timedelta(days=240)), "ISDELETED": False,
        "ORGANIZATIONCODE": ORG, "ORGANIZATIONID": 1, "NAME": f"演示画面分类{i}",
        "DESCRIPTION": "演示数据", "TREECODE": f"{i:02d}", "SORT": i,
    } for i in range(1, 7)]
    canvases = [{
        "ID": f"DEMO-CV-{i:02d}", "CREATIONTIME": ts(TODAY - dt.timedelta(days=200)), "ISDELETED": False,
        "TENANTID": 0, "ORGANIZATIONCODE": ORG, "ORGANIZATIONID": 1,
        "CLASSIFICATIONID": f"DEMO-CVCL-{(i - 1) % 6 + 1:02d}",
        "NAME": f"演示组态画面{i}", "DESCRIPTION": "演示数据", "SORTS": i, "CONTENT": "{}",
    } for i in range(1, 31)]
    components = [{
        "ID": f"DEMO-CP-{i:03d}", "CREATIONTIME": ts(TODAY - dt.timedelta(days=200)), "ISDELETED": False,
        "TENANTID": 0, "CLASSIFICATIONID": f"DEMO-CC-{(i - 1) % 6 + 1:02d}",
        "NAME": f"演示组件{i}", "CONTENT": "{}", "SORT": i, "ISDEFAULT": False, "TYPE": 1,
    } for i in range(1, 101)]
    cvc_refs = [{
        "ID": f"DEMO-CVC-{i:03d}", "CANVASID": f"DEMO-CV-{(i - 1) % 30 + 1:02d}",
        "COMPONENTID": f"DEMO-CP-{(i - 1) % 100 + 1:03d}", "KEY": f"k{i}",
        "INSTANCENAME": f"实例{i}",
    } for i in range(1, 301)]
    personnel = [{
        "ID": f"DEMO-FR-{i:03d}", "CREATIONTIME": ts(TODAY - dt.timedelta(days=180)), "ISDELETED": False,
        "NAME": f"演示人员{i:03d}", "SEX": "男" if i % 2 else "女",
        "IDTYPE": "身份证", "IDNUMBER": f"11010119900101{i:04d}",
        "PHONENUMBER": f"1380000{i:04d}", "CLIENTTYPE": "企业微信",
        "CLIENTID": f"wx_demo_{i:03d}", "AUDITRESULT": 1,
    } for i in range(1, 101)]
    apps = [{
        "ID": f"DEMO-APP-{i:02d}", "CREATIONTIME": ts(TODAY - dt.timedelta(days=150)), "ISDELETED": False,
        "ORGANIZATIONCODE": ORG, "APPNAME": "AIStation 移动端",
        "APPTYPE": "Android" if i % 2 else "iOS", "VERSIONNUMBER": f"2.{i}.0",
        "RELEASETIME": (ts(TODAY - dt.timedelta(days=140 - i * 8)) if i <= 8 else None),
        "REMARK": "演示数据",
    } for i in range(1, 13)]
    await conn.rollback()
    async with conn.begin():
        c0 = await _bulk(conn, "CMMS_CANVASCLASSIFICATION", vclasses)
        c1 = await _bulk(conn, "CMMS_COMPONENTCLASSIFICATION", cclasses)
        c2 = await _bulk(conn, "CMMS_CANVAS", canvases)
        c3 = await _bulk(conn, "CMMS_COMPONENT", components)
        c4 = await _bulk(conn, "CMMS_CANVASCOMPONENT", cvc_refs)
        c5 = await _bulk(conn, "FR_PERSONNELINFO", personnel)
        c6 = await _bulk(conn, "CMCS_APPVERSION", apps)
    print(f"[other] 画面分类 {c0}、组件分类 {c1}、画面 {c2}、组件 {c3}、引用 {c4}、人员 {c5}、版本 {c6}")


async def verify(conn) -> None:
    from sqlalchemy import text

    checks = [
        ("合同/质量/条款", 'SELECT (SELECT count(*) FROM "FUEL_CB_COALCONTRACT"), (SELECT count(*) FROM "FUEL_CB_COALCONTRACTQUALITY"), (SELECT count(*) FROM "FUEL_CB_CONTRACTTEMPITEM")'),
        ("批次 / 已关联合同 / 不同合同", 'SELECT count(*), count(*) FILTER (WHERE "CONTRACTID" IS NOT NULL), count(DISTINCT "CONTRACTID") FROM "FUEL_CMCS_INFACTORYBATCH" WHERE "ISDELETED"=false'),
        ("批次最近90天", 'SELECT count(*) FROM "FUEL_CMCS_INFACTORYBATCH" WHERE "FACTARRIVEDATE" >= CURRENT_DATE - 90'),
        ("采样/制样/化验", 'SELECT (SELECT count(*) FROM "FUEL_CMCS_RCSAMPLING"), (SELECT count(*) FROM "FUEL_CMCS_MAKE"), (SELECT count(*) FROM "FUEL_CMCS_ASSAY")'),
        ("细项化验", 'SELECT (SELECT count(*) FROM "FUEL_CMCS_ELEMENTASSAY"), (SELECT count(*) FROM "FUEL_CMCS_SULFURASSAY"), (SELECT count(*) FROM "FUEL_CMCS_HEATASSAY")'),
        ("结算/明细", 'SELECT (SELECT count(*) FROM "FUEL_CB_COALBALANCE"), (SELECT count(*) FROM "FUEL_CB_COALBALANCEDETAIL")'),
        ("计划", 'SELECT (SELECT count(*) FROM "FUEL_CMCS_PLANMONTH"), (SELECT count(*) FROM "FUEL_CMCS_PLANMONTHDETAIL"), (SELECT count(*) FROM "FUEL_CMCS_PLANDAY")'),
        ("组态/人员/版本", 'SELECT (SELECT count(*) FROM "CMMS_CANVAS"), (SELECT count(*) FROM "FR_PERSONNELINFO"), (SELECT count(*) FROM "CMCS_APPVERSION")'),
    ]
    for label, sql in checks:
        print(f"[verify] {label}: {(await conn.execute(text(sql))).fetchone()}")


async def main() -> None:
    from main import create_app

    create_app()
    engine, ds_id = await _engine()
    from app.plugin.module_ai.query import datasource_core as dc

    print(f"[schema] 同步 {ds_id}: {await dc.sync_datasource_schema(ds_id)}")
    # 指标/术语/示例/副本专用指标（复用旧脚本里的幂等函数）
    from seed_local_copy_business_data import clone_query_meta, seed_extra_metrics

    await clone_query_meta(ds_id)
    await seed_extra_metrics(ds_id)
    async with engine.connect() as conn:
        await seed(conn)
        await verify(conn)


if __name__ == "__main__":
    asyncio.run(main())
