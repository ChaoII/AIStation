"""补业务辅助表（ds:6）：设备/照片/采样流程/运输/计量/预警/配煤/计划关联。

在 `seed_realistic_business_data.py` 之后运行；只写本地副本，ID 统一 `DEMO-AUX-` 前缀，幂等。
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
TODAY = dt.datetime.combine(dt.date.today(), dt.time())
RNG = random.Random(20261112)
ORG = "00001"
P = "DEMO-AUX-"


def D(v: float) -> Decimal:
    return Decimal(str(round(v, 2)))


def ts(days_ago: int, hour: int = 9) -> dt.datetime:
    return (TODAY - dt.timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0, microsecond=0)


async def _engine():
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query import executor as ex
    from app.plugin.module_ai.query import service as svc

    async with async_db_session() as db:
        ds_id = (await db.execute(text(
            "SELECT id FROM ai_query_datasources WHERE code=:c AND is_deleted=false"
        ), {"c": DS_CODE})).scalar()
    ds = await svc._load_ds(int(ds_id))
    return ex.build_engine(svc._ds_cfg_from_model(ds))


async def bulk(conn, table: str, rows: list[dict]) -> int:
    from sqlalchemy import text

    if not rows:
        return 0
    cols = list(rows[0])
    sql = (f'INSERT INTO "{table}" (' + ",".join(f'"{c}"' for c in cols) + ") VALUES ("
           + ",".join(f":{c}" for c in cols) + ') ON CONFLICT DO NOTHING')
    await conn.execute(text(sql), rows)
    return len(rows)


TABLES = [
    "FUEL_CMCS_SAMPLETAKEDETAIL", "FUEL_CMCS_SAMPLETAKE",
    "FUEL_CMCS_SAMPLECLEARDETAIL", "FUEL_CMCS_SAMPLECLEAR",
    "FUEL_CMCS_SAMPLEINPUT", "FUEL_CMCS_SAMPLEINPUTHISTORY", "FUEL_CMCS_SAMPLEBARREL",
    "FUEL_CMCS_RCCOALSAMPLING", "FUEL_CMCS_RLSAMPLINGDETAIL",
    "FUEL_CMCS_TRANSPORTPICTURE", "FUEL_CMCS_TRAINWEIGHTRECORD", "FUEL_CMCS_TRAINTYPE",
    "FUEL_CMCS_MZSTORAGEQTYSET", "FUEL_CMCS_INFURNACEHISTORY", "FUEL_CMCS_OUTCOALBUNKER",
    "FUEL_CMCS_GOODSTRANSPORT", "FUEL_CMCS_GOODSTYPE",
    "FUEL_CMCS_BUYFUELTRANSPORTDEDUCT", "FUEL_CMCS_BUYFUELTRANSPORT",
    "FUEL_CMCS_AUTOTRUCK", "FUEL_CMCS_CARBLACKLIST", "FUEL_CMCS_EPCCARD",
    "FUEL_CMCS_UNFINISHTRANSPORT", "FUEL_CMCS_TRUCKINFACTORYWAYDETAIL", "FUEL_CMCS_TRUCKINFACTORYWAY",
    "FUEL_CMCS_CONFIRMOPERATIONLOG", "FUEL_CMCS_SIGNALDATA",
    "FUEL_CMCS_TEMPERATUREBARHISTROY", "FUEL_CMCS_TEMPERATUREERRORIMAGE",
    "FUEL_CMCS_SUPEREDITAPPLY", "FUEL_CMCS_INFACTORYBATCHEDIT", "FUEL_CMCS_TRANSPORTEDIT",
    "FUEL_CMCS_APPLETCONFIG", "FUEL_CMCS_APPREMOTECONTROLCMD", "FUEL_CMCS_OPTSUPPLIERHISTORY",
    "FUEL_STG_FUELEARLYWARNINGDETAIL", "FUEL_STG_FUELEARLYWARNING", "FUEL_STG_WARNMESSAGE",
    "FUEL_MIX_COALCONFIGCALCDETAIL", "FUEL_MIX_COALCONFIGCALCSTORAGEDETAIL", "FUEL_MIX_COALCONFIGCALC",
    "FUEL_MIX_HEATEFFICIENCY", "FUEL_MIX_RAWCOALBUNKERSETTING",
    "FUEL_CB_QUALITYSETTING", "FUEL_CB_CONTRACTTEMPITEMZONE", "FUEL_CB_COALBALANCEDETAILBATCH",
    "FUEL_CMCS_PURCHASEMONTHINFURNACE",
    "CMMS_FACILITY", "FR_PERSONNELPHOTO",
    "FUEL_INF_BELTSAMPLEUNLOADCMD", "FUEL_INF_EQUINFSAMPLEBARREL", "FUEL_INF_MAKERCONTROLCMD",
    "FUEL_INF_MAKERPLAN", "FUEL_INF_QCJXCYUNLOADCMD", "FUEL_MIX_MUTERCOALSETTING",
    "FUEL_STG_DLJCMD", "FUEL_STG_FUELTRANSFER", "FUEL_STG_OUTMINQTY",
    "FUEL_STG_PMYCMDRESULT", "FUEL_STG_RATIOINFO", "FUEL_STG_STORAGETOSILODETAIL",
]


async def reset(conn) -> None:
    from sqlalchemy import text

    for t in TABLES:
        await conn.execute(text(f'DELETE FROM "{t}" WHERE "ID" LIKE \'{P}%\''))
    await conn.commit()


async def refs(conn):
    from sqlalchemy import text

    batches = (await conn.execute(text(
        'SELECT "ID","SUPPLIERID","MINEID","FUELKINDID","SUPPLIERNAME","MINENAME","FUELKINDNAME" '
        'FROM "FUEL_CMCS_INFACTORYBATCH" WHERE "ID" LIKE \'DEMO-B-%\' ORDER BY "ID"'
    ))).fetchall()
    samplings = (await conn.execute(text(
        'SELECT "ID","INFACTORYBATCHID","SAMPLECODE","SAMPLINGDATE" FROM "FUEL_CMCS_RCSAMPLING" '
        'WHERE "ID" LIKE \'DEMO-SP-%\' ORDER BY "ID"'
    ))).fetchall()
    makes = (await conn.execute(text(
        'SELECT "ID","SAMPLINGID","MAKECODE","MAKEDATE" FROM "FUEL_CMCS_MAKE" '
        'WHERE "ID" LIKE \'DEMO-MK-%\' ORDER BY "ID"'
    ))).fetchall()
    balances = (await conn.execute(text(
        'SELECT d."ID", d."BALANCEID", b."BALANCEDATE", d."CONTRACTPRICE", d."RAILLOST" '
        'FROM "FUEL_CB_COALBALANCEDETAIL" d JOIN "FUEL_CB_COALBALANCE" b ON b."ID"=d."BALANCEID" '
        'WHERE d."ID" LIKE \'DEMO-BALD2-%\' ORDER BY d."ID"'
    ))).fetchall()
    personnel = (await conn.execute(text(
        'SELECT "ID" FROM "FR_PERSONNELINFO" WHERE "ID" LIKE \'DEMO-FR-%\' ORDER BY "ID"'
    ))).fetchall()
    temp_items = (await conn.execute(text(
        'SELECT "ID" FROM "FUEL_CB_CONTRACTTEMPITEM" WHERE "ID" LIKE \'DEMO-TI-%\' ORDER BY "ID"'
    ))).fetchall()
    purchases = (await conn.execute(text(
        'SELECT "ID" FROM "FUEL_CMCS_PURCHASEMONTH" WHERE "ID" LIKE \'DEMO-PU-%\' ORDER BY "ID"'
    ))).fetchall()
    transports = (await conn.execute(text(
        'SELECT "ID" FROM "FUEL_CMCS_TRANSPORT" WHERE "ISDELETED"=false ORDER BY "ID" LIMIT 800'
    ))).fetchall()
    rls = (await conn.execute(text(
        'SELECT "ID" FROM "FUEL_CMCS_RLSAMPLING" WHERE "ISDELETED"=false ORDER BY "ID" LIMIT 400'
    ))).fetchall()
    storages = (await conn.execute(text(
        'SELECT "ID","UNITNAME" FROM "FUEL_STG_FUELSTORAGE" WHERE "ISDELETED"=false ORDER BY "ID"'
    ))).fetchall()
    kinds = (await conn.execute(text(
        'SELECT "ID","NAME" FROM "FUEL_CMCS_FUELKIND" WHERE "ISDELETED"=false ORDER BY "ID"'
    ))).fetchall()
    return batches, samplings, makes, balances, personnel, temp_items, purchases, transports, rls, storages, kinds


async def seed(conn) -> None:
    from sqlalchemy import text

    (batches, samplings, makes, balances, personnel, temp_items,
     purchases, transports, rls, storages, kinds) = await refs(conn)
    print(f"[aux-ref] batches={len(batches)} sampling={len(samplings)} make={len(makes)} "
          f"transport={len(transports)} rls={len(rls)} storage={len(storages)}")
    if not batches or not samplings:
        raise SystemExit("主数据不完整，先跑 seed_realistic_business_data.py")
    await reset(conn)

    def bmeta(i):
        b = batches[i % len(batches)]
        return b

    # ---------- 设备 / 人员照片 ----------
    facilities = []
    for i in range(1, 11):
        facilities.append({
            "ID": f"{P}FAC-{i:02d}", "CREATIONTIME": ts(300), "NAME": f"演示设备{i:02d}",
            "ORGANIZATIONCODE": ORG, "SORT": i, "TREECODE": f"F{i:02d}",
            "ISACTIVE": True, "KKSCODE": f"KKS{i:02d}",
        })
    photos = [{
        "ID": f"{P}PH-{i:03d}", "CREATIONTIME": ts(200), "PERSONNELID": personnel[(i - 1) % len(personnel)][0],
        "FACEPHOTO_BASE64": None,
    } for i in range(1, len(personnel) + 1)] if personnel else []
    await conn.rollback()
    async with conn.begin():
        n_fac = await bulk(conn, "CMMS_FACILITY", facilities)
        n_ph = await bulk(conn, "FR_PERSONNELPHOTO", photos)
        # 把已有测点挂到演示设备上（原来 FACILITYID 为空）
        await conn.execute(text(
            'UPDATE "CMMS_POINT" p SET "FACILITYID" = f."ID" FROM ('
            'SELECT "ID", row_number() OVER (ORDER BY "ID") rn FROM "CMMS_FACILITY") f '
            'WHERE p."FACILITYID" IS NULL AND (abs(hashtext(p."ID")) % 10) + 1 = f.rn'
        ))
    print(f"[aux] 设备 {n_fac}、人员照片 {n_ph}")

    # ---------- 采样流程 ----------
    barrels = [{
        "ID": f"{P}SB-{i:02d}", "CREATIONTIME": ts(250), "BARRELNAME": f"样桶{i:02d}",
        "BARRELCODE": f"B{i:02d}", "ISUSE": True, "ORGANIZATIONCODE": ORG, "ISDELETED": False,
    } for i in range(1, 11)]
    sinput, shist, stake, staked, sclear, scleard = [], [], [], [], [], []
    for i, (_sid, bid, code, when) in enumerate(samplings, start=1):
        b = bmeta(i - 1)
        sinput.append({
            "ID": f"{P}SI-{i:03d}", "CREATIONTIME": when, "ISDELETED": False,
            "MACHINENAME": "采样机01", "SAMPLECODE": code, "SAMPLETYPE": "全水分样",
            "INPUTTIME": when, "INPUTPLE": "演示采样员", "DATAFLAG": "0",
            "BATCHID": bid, "SUPPLIERID": b[1], "MINEID": b[2], "FUELKINDID": b[3],
            "SAMPLEWEIGHT": D(RNG.randint(20, 40)), "MAKEID": makes[(i - 1) % len(makes)][0] if makes else None,
            "ORGANIZATIONCODE": ORG,
        })
        shist.append({
            "ID": f"{P}SH-{i:03d}", "CREATIONTIME": when, "ISDELETED": False,
            "MACHINENAME": "采样机01", "SAMPLECODE": code, "SAMPLETYPE": "全水分样",
            "INPUTTIME": when, "INPUTPLE": "演示采样员", "DATAFLAG": "0",
            "BATCHID": bid, "SUPPLIERID": b[1], "MINEID": b[2], "FUELKINDID": b[3],
            "SAMPLEWEIGHT": D(RNG.randint(20, 40)), "OPERATIONTYPE": "新增", "ORGANIZATIONCODE": ORG,
        })
        mainid = f"{P}ST-{i:03d}"
        stake.append({
            "ID": mainid, "CREATIONTIME": when, "ISDELETED": False,
            "APPLYUSER": "演示采样员", "APPLYTIME": when, "CHECKPLE": "演示班长",
            "CHECKTIME": when + dt.timedelta(minutes=10), "STATUS": 1,
            "WFNAME": "采样取桶", "SAMPLINGSTATION": "1号采样站", "ORGANIZATIONCODE": ORG,
        })
        for j in range(1, 3):
            staked.append({
                "ID": f"{P}STD-{i:03d}-{j}", "CREATIONTIME": when, "ISDELETED": False,
                "MAINID": mainid, "MACHINENAME": "采样机01", "SAMPLECODE": code,
                "SAMPLETYPE": "全水分样", "INPUTTIME": when, "DATAFLAG": "0",
                "BATCHID": bid, "SUPPLIERID": b[1], "MINEID": b[2], "FUELKINDID": b[3],
                "SAMPLEWEIGHT": D(RNG.randint(10, 20)), "ORGANIZATIONCODE": ORG,
            })
        cmain = f"{P}SC-{i:03d}"
        sclear.append({
            "ID": cmain, "CREATIONTIME": when, "ISDELETED": False, "ORGANIZATIONCODE": ORG,
            "APPLYTIME": when, "CHECKPLE": "演示班长", "CHECKTIME": when + dt.timedelta(minutes=15),
            "STATUS": 1, "WFNAME": "采样清桶", "SAMPLINGSTATION": "1号采样站",
            "APPLYUSER": "演示采样员", "REMARK": "演示清桶",
        })
        for j in range(1, 3):
            scleard.append({
                "ID": f"{P}SCD-{i:03d}-{j}", "CREATIONTIME": when, "ISDELETED": False,
                "ORGANIZATIONCODE": ORG, "MACHINENAME": "采样机01", "SAMPLECODE": code,
                "SAMPLETYPE": "全水分样", "DATAFLAG": "0", "MAINID": cmain,
                "BATCHID": bid, "SUPPLIERID": b[1], "MINEID": b[2], "FUELKINDID": b[3],
                "SAMPLEWEIGHT": D(RNG.randint(5, 12)),
            })
    rccoal = [{
        "ID": f"{P}RCS-{i:03d}", "CREATIONTIME": when, "ISDELETED": False,
        "MAKECODE": makes[(i - 1) % len(makes)][2] if makes else "",
        "SAMPLINGCODE": code, "SAMPLINGTIME": when, "SAMPLINGUSERNAME": "演示采样员",
        "ASSAYUSERNAME": "演示化验员", "ORGANIZATIONCODE": ORG,
    } for i, (_sid, _bid, code, when) in enumerate(samplings, start=1)]
    rlsd = [{
        "ID": f"{P}RLD-{i:03d}", "CREATIONTIME": ts(60), "ISDELETED": False,
        "BARRELCODE": f"T{i:03d}", "SAMPLEWEIGHT": D(RNG.randint(10, 30)),
        "SAMPLECOUNT": 1, "ALLSAMPLEWEIGHT": D(RNG.randint(10, 30)),
        "SAMPLINGID": rls[(i - 1) % len(rls)][0] if rls else None, "SAMPLERNAME": "演示采样员",
        "SAMPLETYPE": "分析样", "BARRELLINGTIME": ts(60), "ORDERNUMBER": 1, "ORGANIZATIONCODE": ORG,
    } for i in range(1, 301)] if rls else []
    await conn.rollback()
    async with conn.begin():
        n1 = await bulk(conn, "FUEL_CMCS_SAMPLEBARREL", barrels)
        n2 = await bulk(conn, "FUEL_CMCS_SAMPLEINPUT", sinput)
        n3 = await bulk(conn, "FUEL_CMCS_SAMPLEINPUTHISTORY", shist)
        n4 = await bulk(conn, "FUEL_CMCS_SAMPLETAKE", stake)
        n5 = await bulk(conn, "FUEL_CMCS_SAMPLETAKEDETAIL", staked)
        n6 = await bulk(conn, "FUEL_CMCS_SAMPLECLEAR", sclear)
        n7 = await bulk(conn, "FUEL_CMCS_SAMPLECLEARDETAIL", scleard)
        n8 = await bulk(conn, "FUEL_CMCS_RCCOALSAMPLING", rccoal)
        n9 = await bulk(conn, "FUEL_CMCS_RLSAMPLINGDETAIL", rlsd)
    print(f"[aux] 样桶 {n1}、采样录入 {n2}/{n3}、取桶 {n4}/{n5}、清桶 {n6}/{n7}、煤样 {n8}、入炉明细 {n9}")

    # ---------- 运输 / 计量 ----------
    pics = []
    if transports:
        for i in range(1, 601):
            t = transports[(i - 1) % len(transports)][0]
            pics.append({
                "ID": f"{P}TP-{i:03d}", "CREATIONTIME": ts(30), "ISDELETED": False,
                "ORGANIZATIONCODE": ORG, "TRANSPORTID": t,
                "CAPTURETYPE": "入厂" if i % 2 else "出场", "CAPTURETIME": ts(30),
                "PICTUREPATH": f"/demo/transport/{i:04d}.jpg", "ISUPLOAD": True,
            })
    traintypes = [{
        "ID": f"{P}TT-{i:02d}", "CREATIONTIME": ts(400), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "TYPENAME": f"C{60 + i}型", "RATEDLOAD": D(60 + i), "TRAINWIDTH": D(3.1),
        "TRAINHEIGHT": D(3.8), "TRAINLONG": D(14), "ISENABLE": True,
    } for i in range(1, 6)]
    weights = []
    for i in range(1, 301):
        b = bmeta(i - 1)
        weights.append({
            "ID": f"{P}TW-{i:03d}", "CREATIONTIME": ts(20), "ISDELETED": False,
            "TRAINNUMBER": f"L{i:05d}", "TRAINTYPE": f"C{60 + (i % 5) + 1}型",
            "TICKETWEIGHT": D(RNG.randint(3000, 5000)), "GROSSWEIGHT": D(RNG.randint(3500, 5500)),
            "SKINWEIGHT": D(1200), "STANDARDWEIGHT": D(RNG.randint(2000, 4000)),
            "MARGINWEIGHT": D(RNG.randint(-50, 50)), "ARRIVETIME": ts(20),
            "GROSSTIME": ts(20), "SKINTIME": ts(20), "LEAVETIME": ts(19),
            "SUPPLIERNAME": b[4], "MINENAME": b[5], "FUELKIND": b[6],
            "ORDERNUMBER": i, "ORGANIZATIONCODE": ORG,
        })
    await conn.rollback()
    async with conn.begin():
        p1 = await bulk(conn, "FUEL_CMCS_TRANSPORTPICTURE", pics)
        p2 = await bulk(conn, "FUEL_CMCS_TRAINTYPE", traintypes)
        p3 = await bulk(conn, "FUEL_CMCS_TRAINWEIGHTRECORD", weights)
    print(f"[aux] 运输照片 {p1}、车型 {p2}、火车计量 {p3}")

    # ---------- 预警 / 库存阈值 ----------
    qsets = [{
        "ID": f"{P}QS-{i:02d}", "CREATIONTIME": ts(90), "ISDELETED": False,
        "FUELKINDID": kinds[(i - 1) % len(kinds)][0], "SETDATE": ts(90),
        "LIMITQTY": D(RNG.randint(5000, 20000)), "ORGANIZATIONCODE": ORG,
    } for i in range(1, 11)]
    warns = [{
        "ID": f"{P}EW-{i:02d}", "CREATIONTIME": ts(120), "ISDELETED": False,
        "ORGANIZATIONCODE": ORG, "TYPE": "存煤量" if i % 2 else "煤质",
        "REMARK": f"演示预警规则{i}",
    } for i in range(1, 11)]
    wdetails = [{
        "ID": f"{P}EWD-{i:03d}", "CREATIONTIME": ts(120), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "CONDITION": ">", "ISPOLICE": True, "COLOR": "#F56C6C", "STARTVALUE": D(0),
        "ENDVALUE": D(RNG.randint(10000, 30000)), "CODETITLE": "存煤量下限",
        "EARLYWARNINGID": warns[(i - 1) % len(warns)]["ID"], "AREANAME": "煤场",
        "ORDERNUMBER": i % 5 + 1,
    } for i in range(1, 31)]
    msgs = [{
        "ID": f"{P}WM-{i:03d}", "CREATIONTIME": ts(i % 30), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "WARNTYPE": "存量预警", "STORAGEAREA": "煤场", "WARNVALUE": str(RNG.randint(8000, 20000)),
        "OVERVALUE": str(RNG.randint(1000, 3000)), "STATUS": 0 if i % 3 else 1,
        "MESSAGE": f"演示预警消息{i}", "WARNDATE": ts(i % 30), "UNITSHAPE": "条形",
    } for i in range(1, 31)]
    await conn.rollback()
    async with conn.begin():
        q1 = await bulk(conn, "FUEL_CMCS_MZSTORAGEQTYSET", qsets)
        q2 = await bulk(conn, "FUEL_STG_FUELEARLYWARNING", warns)
        q3 = await bulk(conn, "FUEL_STG_FUELEARLYWARNINGDETAIL", wdetails)
        q4 = await bulk(conn, "FUEL_STG_WARNMESSAGE", msgs)
    print(f"[aux] 存煤阈值 {q1}、预警规则 {q2}/{q3}、预警消息 {q4}")

    # ---------- 配煤 / 入炉 ----------
    heff = [{
        "ID": f"{P}HE-{i:02d}", "CREATIONTIME": ts(30 * i), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "TRE": D(RNG.uniform(80, 92)), "PAT": D(RNG.uniform(100, 140)),
        "TA": D(RNG.uniform(120, 160)), "MIXCOALQ": D(RNG.randint(3000, 6000)),
        "MIXCOALS": D(RNG.uniform(0.5, 1.2)), "MIXCOALA": D(RNG.uniform(15, 30)),
        "MIXCOALV": D(RNG.uniform(25, 40)), "RESULT": D(RNG.uniform(85, 92)),
    } for i in range(1, 13)]
    bunker_set = [{
        "ID": f"{P}BS-{i:02d}", "CREATIONTIME": ts(60), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "GENSETID": f"GEN{i:02d}", "MAXLOAD": D(600), "MINLOAD": D(300),
        "RAWCOALBUNKERIDS": ",".join(f"B{j:02d}" for j in range(1, 7)),
        "RUNS": 1, "ORDERS": i,
    } for i in range(1, 11)]
    calcs = [{
        "ID": f"{P}CC-{i:02d}", "CREATIONTIME": ts(30 * i), "DATADATE": ts(30 * i),
        "STAGES": "计算完成", "REMARK": "演示配煤计算",
    } for i in range(1, 13)]
    calcd, calcsd = [], []
    for i in range(1, 13):
        cid = f"{P}CC-{i:02d}"
        for j in range(1, 6):
            stor = storages[(j - 1) % len(storages)]
            calcd.append({
                "ID": f"{P}CCD-{i:02d}-{j}", "CREATIONTIME": ts(30 * i), "COALCONFIGCALCID": cid,
                "GENSETID": f"GEN{j:02d}", "GENSETNAME": f"{j}号机组", "MMNUM": j,
                "MMNAMES": f"磨煤机{j}", "STORAGETYPE": "煤场", "STORAGEID": stor[0],
                "STORAGENAME": stor[1], "FUELKINDNAME": kinds[(j - 1) % len(kinds)][1],
                "RATIO": D(RNG.uniform(10, 30)), "QTY": D(RNG.randint(500, 1500)),
                "QCAL": D(RNG.randint(4500, 5200)), "VDAF": D(30), "AD": D(20), "STAD": D(0.8),
                "SORT": j,
            })
            calcsd.append({
                "ID": f"{P}CCSD-{i:02d}-{j}", "CREATIONTIME": ts(30 * i), "COALCONFIGCALCID": cid,
                "STORAGETYPE": "煤场", "STORAGEID": stor[0], "STORAGENAME": stor[1],
                "FUELKINDNAME": kinds[(j - 1) % len(kinds)][1], "QCAL": D(RNG.randint(4500, 5200)),
                "VDAF": D(30), "AD": D(20), "STAD": D(0.8), "SORT": j,
            })
    infurn = [{
        "ID": f"{P}IF-{i:03d}", "CREATIONTIME": ts(i % 60), "TIME": ts(i % 60, 10),
        "BELTNAME": f"{i % 3 + 1}号皮带", "STORAGEID": storages[i % len(storages)][0],
        "STORAGENAME": storages[i % len(storages)][1], "RULE": "配煤",
    } for i in range(1, 301)]
    outb = [{
        "ID": f"{P}OB-{i:03d}", "CREATIONTIME": ts(i % 60), "BUNKERID": storages[i % len(storages)][0],
        "STARTTIME": ts(i % 60, 8), "ENDTIME": ts(i % 60, 12), "QTY": D(RNG.randint(100, 600)),
    } for i in range(1, 301)]
    await conn.rollback()
    async with conn.begin():
        h1 = await bulk(conn, "FUEL_MIX_HEATEFFICIENCY", heff)
        h2 = await bulk(conn, "FUEL_MIX_RAWCOALBUNKERSETTING", bunker_set)
        h3 = await bulk(conn, "FUEL_MIX_COALCONFIGCALC", calcs)
        h4 = await bulk(conn, "FUEL_MIX_COALCONFIGCALCDETAIL", calcd)
        h5 = await bulk(conn, "FUEL_MIX_COALCONFIGCALCSTORAGEDETAIL", calcsd)
        h6 = await bulk(conn, "FUEL_CMCS_INFURNACEHISTORY", infurn)
        h7 = await bulk(conn, "FUEL_CMCS_OUTCOALBUNKER", outb)
    print(f"[aux] 热效率 {h1}、原煤仓设置 {h2}、配煤计算 {h3}/{h4}/{h5}、入炉历史 {h6}、出仓 {h7}")

    # ---------- 合同质量 / 结算批次 ----------
    qsetting = [{
        "ID": f"{P}QSG-{i:02d}", "CREATIONTIME": ts(360), "ISDELETED": False,
        "ORDERNUMBER": i, "ORGANIZATIONCODE": ORG, "CODE": f"Q{i:02d}",
        "NAME": f"演示质量项{i}", "UNIT": "%", "SHOWCONTRACT": "1",
        "SHOWCONTRACTTEMPLATE": "1", "SHOWBALANCE": "1",
    } for i in range(1, 11)]
    zones = []
    for i in range(1, min(300, len(temp_items) * 1) + 1):
        ti = temp_items[(i - 1) % len(temp_items)][0]
        zones.append({
            "ID": f"{P}TZ-{i:03d}", "CREATIONTIME": ts(300), "ISDELETED": False,
            "STANDARDVALUE": D(RNG.randint(4000, 5600)), "MINVALUE": D(4000), "MAXVALUE": D(5600),
            "TEMPLATEITEMID": ti, "ORDERNUMBER": i % 12 + 1, "ORGANIZATIONCODE": ORG,
            "LEFTOPER": ">=", "RIGHTOPER": "<=", "ITEMKIND": "煤质", "UNIT": "Kcal/kg",
            "ZONETYPE": "区间",
        })
    bdb = []
    for i, (did, _bid, bdate, price, raillost) in enumerate(balances, start=1):
        b = bmeta(i - 1)
        bdb.append({
            "ID": f"{P}BDB-{i:03d}", "CREATIONTIME": bdate, "BALANCEDETAILID": did,
            "INFACTORYBATCHID": b[0], "BATCH": f"DEMO-{i:03d}",
            "BALANCEQTY": D(RNG.randint(500, 1500)), "CONTRACTPRICE": price,
            "COALPRICE": price + 15, "RAILLOST": raillost, "CHECKQTY": D(RNG.randint(500, 1500)),
            "ISDELETED": False, "ORDERNUMBER": 1, "ORGANIZATIONCODE": ORG,
        })
    await conn.rollback()
    async with conn.begin():
        z1 = await bulk(conn, "FUEL_CB_QUALITYSETTING", qsetting)
        z2 = await bulk(conn, "FUEL_CB_CONTRACTTEMPITEMZONE", zones)
        z3 = await bulk(conn, "FUEL_CB_COALBALANCEDETAILBATCH", bdb)
    print(f"[aux] 质量设置 {z1}、模板区间 {z2}、结算批次 {z3}")

    # ---------- 运输业务 / 车辆 ----------
    gtypes = [{
        "ID": f"{P}GT-{i:02d}", "CREATIONTIME": ts(400), "ISDELETED": False,
        "TREECODE": f"G{i:02d}", "GOODSNAME": f"物料{i}", "ORDERNUMBER": i, "ISVALID": True,
    } for i in range(1, 11)]
    gtrans = [{
        "ID": f"{P}GTR-{i:03d}", "CREATIONTIME": ts(20), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "GOODSTYPEID": gtypes[(i - 1) % len(gtypes)]["ID"], "SERIALNUMBER": f"G{i:05d}",
        "CARNUMBER": f"晋A{i:05d}", "FIRSTWEIGHT": D(RNG.randint(20000, 30000)),
        "SECONDWEIGHT": D(RNG.randint(10000, 15000)), "SUTTLEWEIGHT": D(RNG.randint(8000, 15000)),
        "INFACTORYTIME": ts(20), "FIRSTTIME": ts(20), "SECONDTIME": ts(20), "OUTFACTORYTIME": ts(19),
        "SUPPLYUNITNAME": "演示供应单位", "RECEIVEUNITNAME": "演示收货单位",
        "GOODSTYPENAME": gtypes[(i - 1) % len(gtypes)]["GOODSNAME"], "ISUSE": True, "ISFINISH": True,
    } for i in range(1, 51)]
    autotrucks = [{
        "ID": f"{P}AT-{i:02d}", "CREATIONTIME": ts(300), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "CARNUMBER": f"晋B{i:05d}", "DRIVER": f"司机{i}", "ISUSE": True,
        "STANDARDWEIGHT": D(30), "EPCCARDID": f"{P}EPC-{i:02d}",
    } for i in range(1, 11)]
    epcs = [{
        "ID": f"{P}EPC-{i:02d}", "CREATIONTIME": ts(300), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "CARDNUMBER": f"EPC{i:05d}", "TAGID": f"TAG{i:05d}",
    } for i in range(1, 21)]
    buy = []
    for i in range(1, 51):
        b = bmeta(i - 1)
        buy.append({
            "ID": f"{P}BT-{i:03d}", "CREATIONTIME": ts(20), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
            "SERIALNUMBER": f"B{i:05d}", "CARNUMBER": f"晋C{i:05d}", "INFACTORYTIME": ts(20),
            "SUPPLIERNAME": b[4], "SUPPLIERID": b[1], "MINENAME": b[5], "MINEID": b[2],
            "FUELKINDNAME": b[6], "FUELKINDID": b[3], "INFACTORYBATCHID": b[0],
            "GROSSWEIGHT": D(RNG.randint(30000, 40000)), "TAREWEIGHT": D(12000),
            "SUTTLEWEIGHT": D(RNG.randint(18000, 28000)), "TICKETWEIGHT": D(RNG.randint(18000, 28000)),
            "GROSSTIME": ts(20), "TARETIME": ts(20), "ISUSE": True, "ISFINISH": True,
        })
    deducts = [{
        "ID": f"{P}BD-{i:02d}", "CREATIONTIME": ts(20), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "TRANSPORTID": buy[(i - 1) % len(buy)]["ID"], "DEDUCTTYPE": "水分扣重",
        "DEDUCTWEIGHT": D(RNG.randint(10, 100)), "REMARK": "演示扣重",
    } for i in range(1, 21)] if buy else []
    black = [{
        "ID": f"{P}BL-{i:02d}", "CREATIONTIME": ts(100), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "CARNO": f"晋D{i:05d}", "DRIVER": f"司机{i}", "JOINTIME": ts(100),
        "JOINUSERNAME": "演示管理员", "JOINREASON": "演示黑名单",
    } for i in range(1, 11)]
    unfin = [{
        "ID": f"{P}UF-{i:02d}", "CREATIONTIME": ts(5), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "TRANSPORTID": buy[(i - 1) % len(buy)]["ID"] if buy else None, "CARTYPE": "汽运",
        "AUTOTRUCKID": autotrucks[(i - 1) % len(autotrucks)]["ID"], "PREVPLACE": "入厂口",
    } for i in range(1, 11)]
    ways = [{
        "ID": f"{P}WY-{i:02d}", "CREATIONTIME": ts(300), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "WAYTYPE": "入厂" if i % 2 else "出厂", "ISUSE": True, "WAYLINE": f"路线{i}",
    } for i in range(1, 11)]
    wdetails = [{
        "ID": f"{P}WD-{i:03d}", "CREATIONTIME": ts(300), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "STEPNAME": f"步骤{i}", "STEPNUMBER": i, "WAYPLACE": "入厂口",
        "TRUCKINFACTORYWAYID": ways[(i - 1) % len(ways)]["ID"],
    } for i in range(1, 41)]
    logs = [{
        "ID": f"{P}LG-{i:03d}", "CREATIONTIME": ts(10), "APPIDENTIFIER": "demo-app",
        "OPERMAN": f"操作员{i % 5}", "OPERTIME": ts(10), "OPERCONTENT": "确认卸煤",
        "OPERCAUSE": "演示",
    } for i in range(1, 51)]
    await conn.rollback()
    async with conn.begin():
        t1 = await bulk(conn, "FUEL_CMCS_GOODSTYPE", gtypes)
        t2 = await bulk(conn, "FUEL_CMCS_GOODSTRANSPORT", gtrans)
        t3 = await bulk(conn, "FUEL_CMCS_AUTOTRUCK", autotrucks)
        t4 = await bulk(conn, "FUEL_CMCS_EPCCARD", epcs)
        t5 = await bulk(conn, "FUEL_CMCS_BUYFUELTRANSPORT", buy)
        t6 = await bulk(conn, "FUEL_CMCS_BUYFUELTRANSPORTDEDUCT", deducts)
        t7 = await bulk(conn, "FUEL_CMCS_CARBLACKLIST", black)
        t8 = await bulk(conn, "FUEL_CMCS_UNFINISHTRANSPORT", unfin)
        t9 = await bulk(conn, "FUEL_CMCS_TRUCKINFACTORYWAY", ways)
        t10 = await bulk(conn, "FUEL_CMCS_TRUCKINFACTORYWAYDETAIL", wdetails)
        t11 = await bulk(conn, "FUEL_CMCS_CONFIRMOPERATIONLOG", logs)
    print(f"[aux] 物料类型 {t1}、物料运输 {t2}、车辆 {t3}、EPC {t4}、采购运输 {t5}/{t6}、黑名单 {t7}、未完成 {t8}、路线 {t9}/{t10}、操作日志 {t11}")

    # ---------- 信号 / 温度 / 审计 / 小程序 ----------
    signals = [{
        "ID": f"{P}SG-{i:03d}", "CREATIONTIME": ts(1), "ISDELETED": False,
        "SIGNALPREFIX": "SIS", "SIGNALNAME": f"测点信号{i}", "SIGNALVALUE": str(round(RNG.uniform(0, 100), 2)),
        "UPDATETIME": ts(1), "ORGANIZATIONCODE": ORG,
    } for i in range(1, 101)]
    temps = [{
        "ID": f"{P}TH-{i:03d}", "CREATIONTIME": ts(1), "PKID": f"PK{i:03d}",
        "MONITOR_UNIT_ID": str(i % 10 + 1), "SHOT_DATETIME": ts(1),
        "MAX_TEMPRATURE": D(RNG.uniform(40, 80)), "MIN_TEMPRATURE": D(RNG.uniform(20, 40)),
        "AVG_TEMPRATURE": D(RNG.uniform(30, 60)), "EQUIPMENT_ID": str(i % 10 + 1),
    } for i in range(1, 101)]
    terrs = [{
        "ID": f"{P}TE-{i:03d}", "CREATIONTIME": ts(1), "PKID": f"PK{i:03d}",
        "IMAGE_ID": f"IMG{i:03d}", "ITEM_URL": f"/demo/temp/{i:03d}.jpg",
        "MONITOR_UNIT_ID": str(i % 10 + 1), "MSG_DATETIME": ts(1),
        "MSG_TEXT": "温度异常", "EQUIPMENT_ID": str(i % 10 + 1),
    } for i in range(1, 51)]
    applies = [{
        "ID": f"{P}SA-{i:02d}", "CREATIONTIME": ts(20), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "APPLYTYPE": 1, "APPLYTIME": ts(20), "APPLYREASON": "演示超管申请",
        "WFSTATUS": 1, "WFNAME": "已审批", "OBJECTCODE": "coal_batch",
        "OBJECTID": f"DEMO-B-{i:03d}",
    } for i in range(1, 11)]
    bedit = [{
        "ID": f"{P}BE-{i:03d}", "CREATIONTIME": ts(15), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "MAINID": bmeta(i - 1)[0], "BATCH": f"DEMO-{i:03d}", "EDITTYPE": 1,
        "CHECKQTY": D(RNG.randint(2000, 4000)), "ESTIMATEKCAL": D(RNG.randint(4500, 5200)),
    } for i in range(1, 21)]
    tedit = [{
        "ID": f"{P}TE2-{i:03d}", "CREATIONTIME": ts(15), "ISDELETED": False,
        "INFACTORYBATCHID": bmeta(i - 1)[0], "CHECKQTY": D(RNG.randint(2000, 4000)),
        "RAILLOST": D(RNG.randint(0, 10)), "ORGANIZATIONCODE": ORG,
    } for i in range(1, 21)]
    appcfg = [{
        "ID": f"{P}AC-{i:02d}", "CREATIONTIME": ts(90), "ISDELETED": False,
        "ORGANIZATIONCODE": ORG, "APPIDENTIFIER": "demo-app",
        "CONFIGNAME": f"配置{i}", "CONFIGVALUE": f"值{i}",
    } for i in range(1, 6)]
    cmds = [{
        "ID": f"{P}CM-{i:02d}", "CREATIONTIME": ts(5), "APPIDENTIFIER": "demo-app",
        "CMDCODE": "refresh", "PARAM": "{}", "RESULTCODE": "0", "DATAFLAG": "0",
    } for i in range(1, 21)]
    opt_details = (await conn.execute(text(
        'SELECT "ID" FROM "FUEL_CMCS_OPTSUPPLIERDETAIL" WHERE "ISDELETED"=false ORDER BY "ID" LIMIT 200'
    ))).fetchall()
    ophist = [{
        "ID": f"{P}OH-{i:03d}", "CREATIONTIME": ts(60),
        "CMCSOPTSUPPLIERDETAILID": opt_details[(i - 1) % len(opt_details)][0],
        "FIXPROCUREQTY": D(10000), "MINPROCUREQTY": D(5000), "MAXPROCUREQTY": D(20000),
        "KCAL": D(RNG.randint(4500, 5200)), "S": D(0.8), "V": D(30),
        "PRICE": D(RNG.randint(500, 600)), "FREIGHTPRICE": D(35),
        "STANDARDPRICE": D(505), "HUNDREDKCALPRICE": D(110),
    } for i in range(1, 51)] if opt_details else []
    pmif = [{
        "ID": f"{P}PIF-{i:02d}", "CREATIONTIME": ts(30), "PURCHASEMONTHID": purchases[(i - 1) % len(purchases)][0],
        "FUELSTORAGEID": storages[i % len(storages)][0], "AREACODE": f"A{i:02d}",
        "AREANAME": "煤场", "PLANQTY": D(10000), "FUELPRICE": D(550),
        "KCAL": D(4900), "S": D(0.8), "V": D(30), "SORT": i,
    } for i in range(1, 13)] if purchases else []
    await conn.rollback()
    async with conn.begin():
        s1 = await bulk(conn, "FUEL_CMCS_SIGNALDATA", signals)
        s2 = await bulk(conn, "FUEL_CMCS_TEMPERATUREBARHISTROY", temps)
        s3 = await bulk(conn, "FUEL_CMCS_TEMPERATUREERRORIMAGE", terrs)
        s4 = await bulk(conn, "FUEL_CMCS_SUPEREDITAPPLY", applies)
        s5 = await bulk(conn, "FUEL_CMCS_INFACTORYBATCHEDIT", bedit)
        s6 = await bulk(conn, "FUEL_CMCS_TRANSPORTEDIT", tedit)
        s7 = await bulk(conn, "FUEL_CMCS_APPLETCONFIG", appcfg)
        s8 = await bulk(conn, "FUEL_CMCS_APPREMOTECONTROLCMD", cmds)
        s9 = await bulk(conn, "FUEL_CMCS_OPTSUPPLIERHISTORY", ophist)
        s10 = await bulk(conn, "FUEL_CMCS_PURCHASEMONTHINFURNACE", pmif)
    print(f"[aux] 信号 {s1}、温度 {s2}/{s3}、审计 {s4}/{s5}/{s6}、小程序 {s7}/{s8}、寻优历史 {s9}、采购入炉 {s10}")

    # ---------- 设备指令 / 历史（最后 12 张燃料空表） ----------
    opt_all = (await conn.execute(text(
        'SELECT "ID" FROM "FUEL_CMCS_OPTSUPPLIERDETAIL" ORDER BY "ID" LIMIT 200'
    ))).fetchall()
    ophist = [{
        "ID": f"{P}OH-{i:03d}", "CREATIONTIME": ts(60),
        "CMCSOPTSUPPLIERDETAILID": opt_all[(i - 1) % len(opt_all)][0],
        "FIXPROCUREQTY": D(10000), "MINPROCUREQTY": D(5000), "MAXPROCUREQTY": D(20000),
        "KCAL": D(RNG.randint(4500, 5200)), "S": D(0.8), "V": D(30),
        "PRICE": D(RNG.randint(500, 600)), "FREIGHTPRICE": D(35),
        "STANDARDPRICE": D(505), "HUNDREDKCALPRICE": D(110),
    } for i in range(1, 51)] if opt_all else []
    belt_unload = [{
        "ID": f"{P}BU-{i:02d}", "CREATIONTIME": ts(5), "INTERFACETYPE": "皮带采样",
        "MACHINECODE": "SAMPLE01", "SAMPLECODE": samplings[i % len(samplings)][2],
        "UNLOADTYPE": "卸样", "RESULTCODE": "0", "DATAFLAG": "0",
        "SAMPLINGID": samplings[i % len(samplings)][0],
    } for i in range(1, 21)]
    barrels_cmd = [{
        "ID": f"{P}EQ-{i:02d}", "CREATIONTIME": ts(5), "SAMPLEWEIGHT": D(RNG.randint(10, 30)),
        "BARRELCODE": f"B{i:02d}", "INTERFACETYPE": "采样机", "MACHINECODE": "SAMPLE01",
        "BARRELNUMBER": str(i), "INFACTORYBATCHID": bmeta(i - 1)[0],
        "SAMPLECODE": samplings[i % len(samplings)][2], "SAMPLECOUNT": 1, "ISCURRENT": True,
        "BARRELSTATUS": "1", "UPDATETIME": ts(5), "DATAFLAG": "0", "BARRELTYPE": "全水分",
    } for i in range(1, 21)]
    maker_cmd = [{
        "ID": f"{P}MC-{i:02d}", "CREATIONTIME": ts(5), "INTERFACETYPE": "制样机",
        "MACHINECODE": "MAKE01", "CMDCODE": "start", "MAKECODE": f"ZY{i:04d}",
        "RESULTCODE": "0", "DATAFLAG": "0",
    } for i in range(1, 21)]
    maker_plan = [{
        "ID": f"{P}MP-{i:02d}", "CREATIONTIME": ts(5), "WEIGHT": D(RNG.randint(50, 200)),
        "BARRELWEIGHT": str(RNG.randint(10, 40)), "BARRELNUMBER": str(i), "INTERFACETYPE": "制样机",
        "MACHINECODE": "MAKE01", "INFACTORYBATCHID": bmeta(i - 1)[0],
        "MAKECODE": f"ZY{i:04d}", "FUELKINDNAME": bmeta(i - 1)[6], "MT": "12",
        "MAKETYPE": "分析样", "DATAFLAG": "0",
    } for i in range(1, 21)]
    qcjx = [{
        "ID": f"{P}QX-{i:02d}", "CREATIONTIME": ts(5), "MACHINECODE": "SAMPLE02",
        "SAMPLECODE": samplings[i % len(samplings)][2], "UNLOADTYPE": "卸样",
        "RESULTCODE": "0", "DATAFLAG": "0", "SAMPLINGID": samplings[i % len(samplings)][0],
    } for i in range(1, 21)]
    muter = [{
        "ID": f"{P}MT-{i:02d}", "CREATIONTIME": ts(30), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "COALIDS": ",".join(kinds[(i + j) % len(kinds)][0] for j in range(3)),
        "COALNAMES": ",".join(kinds[(i + j) % len(kinds)][1] for j in range(3)),
        "ORDERNUMBER": i,
    } for i in range(1, 11)]
    dlj = [{
        "ID": f"{P}DL-{i:02d}", "CREATIONTIME": ts(10), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "RECORDDATE": ts(10), "FUELSTORAGEID": storages[i % len(storages)][0],
        "TASKNR": i, "DEVICENO": f"D{i:02d}", "WORKTYPE": 1, "PROCESSFLAG": 2,
        "STARTTIME": ts(10, 8), "ENDTIME": ts(10, 10), "TASKWEIGHT": D(RNG.randint(1000, 3000)),
    } for i in range(1, 21)]
    transfer = [{
        "ID": f"{P}FT-{i:02d}", "CREATIONTIME": ts(10), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "BATCHID": bmeta(i - 1)[0], "FUELUNITIDSOUR": storages[i % len(storages)][0],
        "FUELUNITNAMESOUR": storages[i % len(storages)][1],
        "FUELUNITIDDEST": storages[(i + 1) % len(storages)][0],
        "FUELUNITNAMEDEST": storages[(i + 1) % len(storages)][1],
        "SOURQTY": D(RNG.randint(500, 1500)), "DESTQTY": D(RNG.randint(500, 1500)),
        "TRANSFERQTY": D(RNG.randint(500, 1500)), "RECORDDATE": ts(10),
        "RECORDERNAME": "演示记录员", "ISFINISH": "1", "STATUS": "1",
    } for i in range(1, 21)]
    outmin = [{
        "ID": f"{P}OM-{i:02d}", "CREATIONTIME": ts(10), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "INFACTORYBATCHID": bmeta(i - 1)[0], "QTYOUT": D(RNG.randint(100, 600)),
        "MINSCALENO": 1, "STARTPOINT": 0, "ENDPOINT": 10,
    } for i in range(1, 21)]
    pmy = [{
        "ID": f"{P}PR-{i:02d}", "CREATIONTIME": ts(10), "RESULTTIME": ts(10), "PKID": f"PK{i:02d}",
        "FILEURL": f"/demo/pmy/{i:02d}.jpg", "VOL": D(RNG.randint(100, 500)),
        "HEIGHT": D(RNG.uniform(1, 5)), "AREA": D(RNG.randint(1000, 5000)),
        "WEIGHT": D(RNG.randint(10000, 50000)), "DENSITY": D(0.9), "ISDELETED": False,
    } for i in range(1, 21)]
    ratio = [{
        "ID": f"{P}RI-{i:02d}", "CREATIONTIME": ts(10), "SORT": i, "RATIOINFO": f"比例{i}",
        "STARTSTRAP_6A": D(0), "ENDSTRAP_6A": D(10), "STARTSTRAP_6B": D(10),
        "ENDSTRAP_6B": D(20),
    } for i in range(1, 21)]
    silod = [{
        "ID": f"{P}SD-{i:02d}", "CREATIONTIME": ts(10), "ISDELETED": False, "ORGANIZATIONCODE": ORG,
        "STORAGENAME": storages[i % len(storages)][1], "STORAGEID": storages[i % len(storages)][0],
        "STORAGEQTY": D(RNG.randint(1000, 5000)), "TAKEQTY": D(RNG.randint(500, 2000)),
        "ORDERNUMBER": i, "STARTTIME": ts(10, 8), "ENDTIME": ts(10, 12),
    } for i in range(1, 21)]
    await conn.rollback()
    async with conn.begin():
        f1 = await bulk(conn, "FUEL_CMCS_OPTSUPPLIERHISTORY", ophist)
        f2 = await bulk(conn, "FUEL_INF_BELTSAMPLEUNLOADCMD", belt_unload)
        f3 = await bulk(conn, "FUEL_INF_EQUINFSAMPLEBARREL", barrels_cmd)
        f4 = await bulk(conn, "FUEL_INF_MAKERCONTROLCMD", maker_cmd)
        f5 = await bulk(conn, "FUEL_INF_MAKERPLAN", maker_plan)
        f6 = await bulk(conn, "FUEL_INF_QCJXCYUNLOADCMD", qcjx)
        f7 = await bulk(conn, "FUEL_MIX_MUTERCOALSETTING", muter)
        f8 = await bulk(conn, "FUEL_STG_DLJCMD", dlj)
        f9 = await bulk(conn, "FUEL_STG_FUELTRANSFER", transfer)
        f10 = await bulk(conn, "FUEL_STG_OUTMINQTY", outmin)
        f11 = await bulk(conn, "FUEL_STG_PMYCMDRESULT", pmy)
        f12 = await bulk(conn, "FUEL_STG_RATIOINFO", ratio)
        f13 = await bulk(conn, "FUEL_STG_STORAGETOSILODETAIL", silod)
    print(f"[aux] 寻优历史 {f1}、指令/历史 {f2}/{f3}/{f4}/{f5}/{f6}、混煤 {f7}、堆取料 {f8}、倒垛 {f9}/{f10}/{f11}/{f12}/{f13}")


async def verify(conn) -> None:
    from sqlalchemy import text

    checks = [
        ("设备/照片", 'SELECT (SELECT count(*) FROM "CMMS_FACILITY"), (SELECT count(*) FROM "FR_PERSONNELPHOTO")'),
        ("采样流程", 'SELECT (SELECT count(*) FROM "FUEL_CMCS_SAMPLEINPUT"), (SELECT count(*) FROM "FUEL_CMCS_SAMPLETAKE"), (SELECT count(*) FROM "FUEL_CMCS_SAMPLECLEAR")'),
        ("运输/计量", 'SELECT (SELECT count(*) FROM "FUEL_CMCS_TRANSPORTPICTURE"), (SELECT count(*) FROM "FUEL_CMCS_TRAINWEIGHTRECORD"), (SELECT count(*) FROM "FUEL_CMCS_BUYFUELTRANSPORT")'),
        ("预警/阈值", 'SELECT (SELECT count(*) FROM "FUEL_STG_FUELEARLYWARNING"), (SELECT count(*) FROM "FUEL_STG_WARNMESSAGE"), (SELECT count(*) FROM "FUEL_CMCS_MZSTORAGEQTYSET")'),
        ("配煤", 'SELECT (SELECT count(*) FROM "FUEL_MIX_COALCONFIGCALC"), (SELECT count(*) FROM "FUEL_MIX_HEATEFFICIENCY")'),
        ("合同/结算", 'SELECT (SELECT count(*) FROM "FUEL_CB_QUALITYSETTING"), (SELECT count(*) FROM "FUEL_CB_CONTRACTTEMPITEMZONE"), (SELECT count(*) FROM "FUEL_CB_COALBALANCEDETAILBATCH")'),
        ("其他", 'SELECT (SELECT count(*) FROM "FUEL_CMCS_SIGNALDATA"), (SELECT count(*) FROM "FUEL_CMCS_CONFIRMOPERATIONLOG")'),
        ("孤儿检查", 'SELECT count(*) FROM "FUEL_CMCS_TRANSPORTPICTURE" p WHERE p."ID" LIKE \'DEMO-AUX-%\' AND NOT EXISTS (SELECT 1 FROM "FUEL_CMCS_TRANSPORT" t WHERE t."ID"=p."TRANSPORTID")'),
    ]
    for label, sql in checks:
        print(f"[verify] {label}: {(await conn.execute(text(sql))).fetchone()}")


async def main() -> None:
    from main import create_app

    create_app()
    engine = await _engine()
    async with engine.connect() as conn:
        await seed(conn)
        await verify(conn)


if __name__ == "__main__":
    asyncio.run(main())
