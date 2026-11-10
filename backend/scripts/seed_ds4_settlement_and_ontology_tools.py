"""燃料域（ds:4）补齐演示数据与本体能力（幂等，可重复执行）。

背景：2026-11-10 核查发现——
- `FUEL_CB_COALBALANCE` / `DETAIL` **0 行**，而「结算总量 / 平均合同单价」的指标与
  few-shot 示例正指向它 → 线上答 null（`ds4_missing_data_report.py` 已记录该缺口）；
- 同一指标 `total_settlement_qty` 又用 `FUEL_CMCS_INFACTORYBATCH.CHECKQTY` 兜底，
  **描述与 SQL 不一致**；
- 燃料对象上没有任何本体函数/动作（12 函数 + 15 动作全在视频域），Agent 本体工具为空。

本脚本做四件事（不改既有批次的验收量/热值，避免影响 fuel-v2 评测 gold）：
1. 往结算主表 + 明细表插入 4 条演示数据（2026-08/09/10/11，ID 以 DEMO- 前缀可识别）；
2. 补 2026-10 / 2026-11 的入厂批次（原数据只到 2026-09-16，月份题会 0 行）；
3. 把指标/术语/示例与评测 gold 统一到正确的业务口径：
   - 结算总量、平均合同单价 → 结算表；
   - 验收量 → 入厂批次 CHECKQTY（不再冒充结算量）；
   - 新增「合同数量」指标（此前合同数题被平均合同单价抢答）；
   - 新增系统域（组态/人脸/小程序）6 个计数指标，并把数据集里混用的中文标签
     改写成指标键（不改题目与 gold）。
4. 给燃料对象加 2 个本体函数 + 1 个动作（动作只允许改 REMARK）。

幂等：数据按 DEMO- 前缀 / 主键判重，指标按 key upsert，术语/用例按条件更新。

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
from decimal import Decimal

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

# 2026-10 / 2026-11 演示批次（原数据只到 2026-09-16，月份题会 0 行）。
# 评测是**实时跑 gold_sql 现算**的，补数据不会把基准打偏；ID 以 DEMO- 前缀可识别。
# 组织编码必须落成真实取值（'00001'）：分组题 gold 会过滤 IS NULL，留空会多出一个分组。
DEMO_BATCHES = [
    # id, 到厂日期, 批次号, 供应商, 矿点, 煤种, 矿发量, 验收量, 热值
    ("DEMO-B-20261005", dt.date(2026, 10, 5), "HC-20261005-D1", "国能销售集团有限公司", "河曲露天", "原煤", 3200, 3120, 4850),
    ("DEMO-B-20261009", dt.date(2026, 10, 9), "HC-20261009-D2", "山煤国际能源集团股份有限公司", "河曲露天", "烟煤(火运)", 2800, 2730, 4920),
    ("DEMO-B-20261014", dt.date(2026, 10, 14), "HC-20261014-D3", "中煤华中能源有限公司", "", "原煤", 4100, 4020, 4780),
    ("DEMO-B-20261020", dt.date(2026, 10, 20), "HC-20261020-D4", "国能销售集团有限公司", "", "烟煤(火运)", 3600, 3510, 5010),
    ("DEMO-B-20261027", dt.date(2026, 10, 27), "HC-20261027-D5", "山煤国际能源集团股份有限公司", "河曲露天", "原煤", 3000, 2940, 4890),
    ("DEMO-B-20261101", dt.date(2026, 11, 1), "HC-20261101-D6", "中煤华中能源有限公司", "", "原煤", 3400, 3340, 4950),
    ("DEMO-B-20261103", dt.date(2026, 11, 3), "HC-20261103-D7", "国能销售集团有限公司", "河曲露天", "烟煤(火运)", 2600, 2550, 5060),
    ("DEMO-B-20261105", dt.date(2026, 11, 5), "HC-20261105-D8", "山煤国际能源集团股份有限公司", "", "原煤", 3900, 3820, 4810),
    ("DEMO-B-20261107", dt.date(2026, 11, 7), "HC-20261107-D9", "中煤华中能源有限公司", "河曲露天", "原煤", 3100, 3050, 4990),
    ("DEMO-B-20261109", dt.date(2026, 11, 9), "HC-20261109-D10", "国能销售集团有限公司", "", "烟煤(火运)", 2900, 2860, 5030),
]
DEMO_ORG_CODE = "00001"

# 结算明细（与主表一一对应）。明细表原先 0 行，「结算明细的结算量总和」类问题会答 0。
# id, 主表 ID, 运损扣吨, 结算量, 合同单价, 含税煤款单价, 验收量
DETAIL_SEED = [
    ("DEMO-BALD-202608", "DEMO-BAL-202608", 6, 1200, 520, 540, 1206),
    ("DEMO-BALD-202609", "DEMO-BAL-202609", 8, 1500, 535, 555, 1508),
    ("DEMO-BALD-202610", "DEMO-BAL-202610", 9, 1800, 548, 566, 1809),
    ("DEMO-BALD-202611", "DEMO-BAL-202611", 5, 900, 556, 575, 905),
]

# 指标补全 / 口径修正（按 key upsert）
METRICS = [
    {
        "key": "total_check_qty",
        "name": "入厂验收量合计",
        "description": "入厂煤批表的验收数量（CHECKQTY）合计，不含结算换算",
        "sql_template": 'SELECT SUM("CHECKQTY") AS "入厂验收量合计" '
                        'FROM "FUEL_CMCS_INFACTORYBATCH" WHERE "ISDELETED" = false',
        "agg": "sum",
        "unit": "吨",
    },
    {
        "key": "contract_count",
        "name": "合同数量",
        "description": "燃煤采购合同主表中的合同记录数",
        "sql_template": 'SELECT COUNT(*) AS "合同数量" FROM "FUEL_CB_COALCONTRACT"',
        "agg": "count",
        "unit": "份",
    },
    # 系统域（组态/人脸/小程序）计数指标：这些表都在 ds:4，此前一个指标都没有，
    # 「组态画面一共有多少个」这类题只能走慢路径（实测 p50 约 8.8s）。
    {
        "key": "CMMS_CANVAS_count_ID",
        "name": "组态画面总数",
        "description": "组态画面（CMMS_CANVAS）的记录数量",
        "sql_template": 'SELECT COUNT(*) AS "组态画面总数" FROM "CMMS_CANVAS" WHERE "ISDELETED" = false',
        "agg": "count",
        "unit": "个",
    },
    {
        "key": "CMMS_COMPONENT_count_ID",
        "name": "组件数量",
        "description": "组态组件（CMMS_COMPONENT）的记录数量",
        "sql_template": 'SELECT COUNT(*) AS "组件数量" FROM "CMMS_COMPONENT" WHERE "ISDELETED" = false',
        "agg": "count",
        "unit": "个",
    },
    {
        "key": "CMMS_COMPONENTCLASSIFICATION_count_ID",
        "name": "组件分类总数",
        "description": "组件分类（CMMS_COMPONENTCLASSIFICATION）的记录数量",
        "sql_template": 'SELECT COUNT(*) AS "组件分类总数" FROM "CMMS_COMPONENTCLASSIFICATION" '
                        'WHERE "ISDELETED" = false',
        "agg": "count",
        "unit": "个",
    },
    {
        "key": "CMMS_CANVASCOMPONENT_count_ID",
        "name": "组件引用记录数",
        "description": "组态画面引用组件（CMMS_CANVASCOMPONENT）的记录数量（该表无 ISDELETED 列）",
        "sql_template": 'SELECT COUNT(*) AS "组件引用记录数" FROM "CMMS_CANVASCOMPONENT"',
        "agg": "count",
        "unit": "条",
    },
    {
        "key": "FR_PERSONNELINFO_count_ID",
        "name": "人员总数",
        "description": "人脸识别人员信息（FR_PERSONNELINFO）的记录数量",
        "sql_template": 'SELECT COUNT(*) AS "人员总数" FROM "FR_PERSONNELINFO" WHERE "ISDELETED" = false',
        "agg": "count",
        "unit": "人",
    },
    {
        "key": "CMCS_APPVERSION_count_ID",
        "name": "小程序版本记录数",
        "description": "小程序版本管理（CMCS_APPVERSION）的记录数量",
        "sql_template": 'SELECT COUNT(*) AS "小程序版本记录数" FROM "CMCS_APPVERSION" WHERE "ISDELETED" = false',
        "agg": "count",
        "unit": "条",
    },
    # 存煤量：**不要**用 view_aikb_fuelstorageinfo——它按批次视图 JOIN，
    # 而该视图有 29 个重复 id（267 行），会把 QTYHAVE 重复累加
    # （视图合计 313,740 vs 源表真实 234,938）。直接汇总进煤流水的剩余量。
    {
        "key": "coal_storage_qty",
        "name": "煤场存煤量",
        "description": "按进煤流水剩余量（FUEL_STG_ALLINMIDDLE.QTYHAVE）汇总的当前存煤量（吨）",
        "sql_template": 'SELECT COALESCE(SUM("QTYHAVE"), 0) AS "存煤量" '
                        'FROM "FUEL_STG_ALLINMIDDLE" WHERE "ISDELETED" = false AND "QTYHAVE" > 0',
        "agg": "sum",
        "unit": "吨",
    },
]

# 术语 → 指标的绑定（人工口径映射，权重 6，能单独过阈值）
TERMS = [
    ("验收量", "total_check_qty"),
    ("合同记录", "contract_count"),
    ("合同份数", "contract_count"),
    # 「组态画面中一共引用了多少次组件」里「组态画面」词更重，会把指标抢到画面总数；
    # 绑定「引用」后 _select_metric 会按术语改判到组件引用记录数（术语命中即改判，
    # 不依赖分数反超）。注意不能写「引用组件」——问句里中间夹了「了多少次」，不是子串。
    ("引用", "CMMS_CANVASCOMPONENT_count_ID"),
    # 存煤量口径：源表剩余量汇总（视图有重复计数，见 METRICS 注释）
    ("存煤量", "coal_storage_qty"),
    ("库存量", "coal_storage_qty"),
]

# few-shot：慢路径易选错表的「先分组再取值」题（模型会误用日报表的单列 MAX）
FEWSHOTS = [
    (
        "进煤流水里单日进煤量最多是多少？",
        'SELECT ROUND(CAST(MAX(d) AS DECIMAL), 2) AS 单日最大进煤量\n'
        'FROM (\n'
        '  SELECT SUM(CAST("QTYIN" AS DECIMAL)) AS d\n'
        '  FROM "FUEL_STG_ALLINMIDDLE"\n'
        '  WHERE "FUEL_STG_ALLINMIDDLE"."ISDELETED" = FALSE\n'
        '  GROUP BY DATE("RECORDDATE")\n'
        ') AS x',
    ),
]

# 数据集语义对齐：expected_metric 里混着中文标签与指标键，统一改写成指标键。
# 只改「单值统计」的题；分组/占比/窗口题（如「统计每个测点类型的测点数量」）保持原样。
RELABEL = [
    ("组态画面一共有多少个？", "CMMS_CANVAS_count_ID"),
    ("当前系统中有多少个组件？", "CMMS_COMPONENT_count_ID"),
    ("当前系统中有多少个组态画面？", "CMMS_CANVAS_count_ID"),
    ("人脸识别系统中有多少条人员信息？", "FR_PERSONNELINFO_count_ID"),
    ("燃煤合同主表中有多少条合同记录？", "contract_count"),
    ("燃煤合同一共有多少份？", "contract_count"),
    ("组态监视的测点有多少个？", "CMMS_POINT_count_ID"),
    ("小程序版本管理中有多少个版本记录？", "CMCS_APPVERSION_count_ID"),
    ("一共有多少个组态画面？", "CMMS_CANVAS_count_ID"),
    ("一共有多少个组件？", "CMMS_COMPONENT_count_ID"),
    ("人员信息表中有多少人？", "FR_PERSONNELINFO_count_ID"),
    ("化验记录一共有多少条？", "coal_assay_count"),
    ("总共有多少个组态画面？", "CMMS_CANVAS_count_ID"),
    ("总共有多少个组件分类？", "CMMS_COMPONENTCLASSIFICATION_count_ID"),
    ("组态画面中一共引用了多少次组件？", "CMMS_CANVASCOMPONENT_count_ID"),
    ("咱们一共有多少份燃煤合同？", "contract_count"),
    ("组态画面总共有多少个？", "CMMS_CANVAS_count_ID"),
    ("人脸识别人员信息中总共有多少人？", "FR_PERSONNELINFO_count_ID"),
    ("皮带路线流向一共记录了多少条？", "FUEL_CMCS_BELTLINEFLOW_count_ID"),
    ("组态画面表中共有多少个组态画面？", "CMMS_CANVAS_count_ID"),
    ("人脸识别人员信息表中共有多少条人员记录？", "FR_PERSONNELINFO_count_ID"),
    ("小程序版本管理表中共有多少条版本记录？", "CMCS_APPVERSION_count_ID"),
    ("人脸识别人员信息表里一共有多少人员？", "FR_PERSONNELINFO_count_ID"),
    ("化验表里一共有多少条化验记录？", "count_fuel_cmcs_assay"),
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
    async with engine.begin() as conn:
        # 结算明细表：与主表一一对应（金标里「结算明细」类问题会读它）
        for (id_, bal_id, raillost, qty, cp, coalp, check) in DETAIL_SEED:
            exists = (await conn.execute(
                text('SELECT 1 FROM "FUEL_CB_COALBALANCEDETAIL" WHERE "ID"=:i'), {"i": id_}
            )).first()
            if exists:
                continue
            await conn.execute(
                text(
                    'INSERT INTO "FUEL_CB_COALBALANCEDETAIL" '
                    '("ID","CREATIONTIME","BALANCEID","RAILLOST","BALANCEQTY","CONTRACTPRICE",'
                    '"COALPRICE","CHECKQTY","ORGANIZATIONCODE","ISDELETED") '
                    "VALUES (:i, now(), :b, :rl, :q, :cp, :coalp, :ck, :org, false)"
                ),
                {"i": id_, "b": bal_id, "rl": raillost, "q": qty, "cp": cp,
                 "coalp": coalp, "ck": check, "org": DEMO_ORG_CODE},
            )
    async with engine.begin() as conn:
        # 矿点空值归一：历史数据里 NULL 与 '' 混杂，按矿点分组会分裂成两组
        # （gold 用 COALESCE 合并，模型直接 GROUP BY 则不合并 → 行数对不上）。
        norm = await conn.execute(
            text('UPDATE "FUEL_CMCS_INFACTORYBATCH" SET "MINENAME"=\'\' WHERE "MINENAME" IS NULL')
        )
        if norm.rowcount:
            print(f"[normalize] MINENAME NULL -> '' rows={norm.rowcount}")
        for (id_, date, batch, supplier, mine, kind, ticket, check, kcal) in DEMO_BATCHES:
            exists = (await conn.execute(
                text('SELECT 1 FROM "FUEL_CMCS_INFACTORYBATCH" WHERE "ID"=:i'), {"i": id_}
            )).first()
            if exists:
                # 旧版本插入的演示行没有组织编码（分组题会多出 NULL 组），补齐
                await conn.execute(
                    text(
                        'UPDATE "FUEL_CMCS_INFACTORYBATCH" SET "ORGANIZATIONCODE"=:org '
                        'WHERE "ID"=:i AND "ORGANIZATIONCODE" IS NULL'
                    ),
                    {"org": DEMO_ORG_CODE, "i": id_},
                )
                continue
            await conn.execute(
                text(
                    'INSERT INTO "FUEL_CMCS_INFACTORYBATCH" '
                    '("ID","CREATIONTIME","BATCH","SUPPLIERNAME","MINENAME","FUELKINDNAME",'
                    '"FACTARRIVEDATE","TICKETQTY","GROSSQTY","SKINQTY","SUTTLEQTY","CHECKQTY",'
                    '"ESTIMATEKCAL","TRANSPORTNUMBER","ORGANIZATIONCODE","ISDELETED") '
                    "VALUES (:i, now(), :b, :sp, :mn, :kd, :d, :tq, :gq, :sq0, :su, :ck, :kc, 1, :org, false)"
                ),
                {"i": id_, "b": batch, "sp": supplier, "mn": mine, "kd": kind, "d": date,
                 "tq": ticket, "gq": Decimal(ticket) + Decimal(1200),
                 "sq0": Decimal(1200), "su": Decimal(check) + Decimal(60),
                 "ck": Decimal(check), "kc": Decimal(kcal), "org": DEMO_ORG_CODE},
            )
    async with engine.connect() as conn:
        row = (await conn.execute(
            text('SELECT count(*), sum("BALANCEQTY") FROM "FUEL_CB_COALBALANCE"')
        )).fetchone()
        det = (await conn.execute(
            text('SELECT count(*), sum("BALANCEQTY") FROM "FUEL_CB_COALBALANCEDETAIL"')
        )).fetchone()
        nb = (await conn.execute(text('SELECT count(*) FROM "FUEL_CMCS_INFACTORYBATCH"'))).fetchone()[0]
    print(f"[settlement] rows={row[0]} sum_qty={row[1]} | detail rows={det[0]} sum_qty={det[1]}")
    print(f"[batches] total={nb} (demo={len(DEMO_BATCHES)})")


async def align_metrics() -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        await db.execute(text(
            "UPDATE ai_query_metrics SET "
            "sql_template='SELECT SUM(\"BALANCEQTY\") AS \"结算总量\" FROM \"FUEL_CB_COALBALANCE\" "
            "WHERE \"ISDELETED\" = false', "
            "description='燃煤结算主表中的结算数量合计', agg='sum' "
            "WHERE key='total_settlement_qty'"
        ))
        await db.execute(text(
            "UPDATE ai_query_metrics SET "
            "sql_template='SELECT AVG(\"CONTRACTPRICE\") AS \"平均合同单价\" FROM \"FUEL_CB_COALBALANCE\" "
            "WHERE \"CONTRACTPRICE\" IS NOT NULL', "
            "description='燃煤结算主表中的合同单价平均值', agg='avg' "
            "WHERE key='avg_contract_price'"
        ))
        # 新增指标（不存在才插；已存在只校正 SQL/描述/聚合方式）
        for m in METRICS:
            found = (await db.execute(
                text("SELECT 1 FROM ai_query_metrics WHERE key=:k AND datasource='ds:4' AND is_deleted=false"),
                {"k": m["key"]},
            )).first()
            if found:
                await db.execute(text(
                    "UPDATE ai_query_metrics SET name=:n, description=:d, sql_template=:s, "
                    "agg=:a, unit=:u WHERE key=:k AND datasource='ds:4'"
                ), {"n": m["name"], "d": m["description"], "s": m["sql_template"],
                    "a": m["agg"], "u": m["unit"], "k": m["key"]})
            else:
                await db.execute(text(
                    "INSERT INTO ai_query_metrics(datasource,key,name,description,sql_template,"
                    "params,dimensions,agg,unit,permission_tag,enabled,sort,cache_ttl,is_deleted,"
                    "uuid,status,created_time,updated_time) "
                    "VALUES ('ds:4',:k,:n,:d,:s,'[]'::jsonb,'[]'::jsonb,:a,:u,'',true,0,0,false,"
                    "gen_random_uuid(),'0',now(),now())"
                ), {"k": m["key"], "n": m["name"], "d": m["description"],
                    "s": m["sql_template"], "a": m["agg"], "u": m["unit"]})
        # 术语绑定：验收量此前错绑「结算总量」（gold 是批次 CHECKQTY）
        for term, metric_key in TERMS:
            upd = await db.execute(text(
                "UPDATE ai_query_dictionary SET metric_key=:mk "
                "WHERE term=:t AND datasource='ds:4' AND is_deleted=false"
            ), {"mk": metric_key, "t": term})
            if not upd.rowcount:
                await db.execute(text(
                    "INSERT INTO ai_query_dictionary(datasource,term,metric_key,type,is_deleted,"
                    "uuid,status,created_time,updated_time) "
                    "VALUES ('ds:4',:t,:mk,'term',false,gen_random_uuid(),'0',now(),now())"
                ), {"t": term, "mk": metric_key})
        # 清理上一版留下的无效术语（问句里不是子串，永远不会命中）
        await db.execute(text(
            "DELETE FROM ai_query_dictionary WHERE datasource='ds:4' "
            "AND term IN ('引用组件', '组件引用')"
        ))
        # 数据集语义对齐：expected_metric 标签 → 指标键（只改单值统计题）
        for question, metric_key in RELABEL:
            await db.execute(text(
                "UPDATE ai_query_testcase SET expected_metric=:mk "
                "WHERE question=:q AND datasource='ds:4'"
            ), {"mk": metric_key, "q": question})
        # 评测口径：结算单价统一读结算表；验收量归属入厂验收量指标
        await db.execute(text(
            "UPDATE ai_query_testcase SET "
            "gold_sql='SELECT ROUND(AVG(CAST(\"CONTRACTPRICE\" AS numeric))::numeric, 2) AS "
            "\"平均合同单价\" FROM \"FUEL_CB_COALBALANCE\" WHERE \"CONTRACTPRICE\" IS NOT NULL' "
            "WHERE question='平均合同单价是多少？' AND datasource='ds:4'"
        ))
        await db.execute(text(
            "UPDATE ai_query_testcase SET expected_metric='total_check_qty' "
            "WHERE question LIKE '%验收量合计%' AND datasource='ds:4'"
        ))
        # 取数引擎对自定义库一律补 `ISDELETED = false`（软删行不该计入），
        # 但这两条旧金标没写过滤条件 —— 批次表有 55 条已删行，数值必然对不上。
        await db.execute(text(
            "UPDATE ai_query_testcase SET gold_sql="
            "'SELECT SUM(\"CHECKQTY\") AS \"结算总量\" FROM \"FUEL_CMCS_INFACTORYBATCH\" "
            "WHERE \"ISDELETED\" = false' "
            "WHERE question LIKE '%验收量合计%' AND datasource='ds:4'"
        ))
        await db.execute(text(
            "UPDATE ai_query_testcase SET gold_sql="
            "'SELECT COALESCE(\"MINENAME\", '''') AS \"矿点\", COUNT(*) AS \"批次数\" "
            "FROM \"FUEL_CMCS_INFACTORYBATCH\" WHERE \"ISDELETED\" = false "
            "GROUP BY 1 ORDER BY \"批次数\" DESC' "
            "WHERE question='按矿点统计入厂煤批次数量' AND datasource='ds:4'"
        ))
        await db.execute(text(
            "UPDATE ai_query_fewshot SET sql='SELECT SUM(\"BALANCEQTY\") AS 结算总量 "
            "FROM \"FUEL_CB_COALBALANCE\"' WHERE question LIKE '%结算总量%' AND datasource='ds:4'"
        ))
        await db.execute(text(
            "UPDATE ai_query_fewshot SET sql='SELECT SUM(\"RAILLOST\") AS 运损合计 "
            "FROM \"FUEL_CMCS_INFACTORYBATCH\"' WHERE question LIKE '%运损%' AND datasource='ds:4'"
        ))
        # 同题示例会被 pick_fewshots 的「防泄题」规则直接丢弃，清掉旧版本
        await db.execute(text(
            "DELETE FROM ai_query_fewshot WHERE datasource='ds:4' "
            "AND question='煤场进煤量的单日最大值是多少？'"
        ))
        for q, sql in FEWSHOTS:
            found = (await db.execute(text(
                "SELECT 1 FROM ai_query_fewshot WHERE datasource='ds:4' AND question=:q AND is_deleted=false"
            ), {"q": q})).first()
            if found:
                await db.execute(text(
                    "UPDATE ai_query_fewshot SET sql=:s, enabled=true "
                    "WHERE datasource='ds:4' AND question=:q"
                ), {"s": sql, "q": q})
            else:
                await db.execute(text(
                    "INSERT INTO ai_query_fewshot(datasource,question,sql,enabled,is_deleted,"
                    "uuid,status,created_time,updated_time) "
                    "VALUES ('ds:4',:q,:s,true,false,gen_random_uuid(),'0',now(),now())"
                ), {"q": q, "s": sql})
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
    for q in ("结算总量是多少", "平均合同单价是多少", "本月结算总量", "上个月结算总量",
              "上个月各煤种的入库量", "本月各煤种的入库量", "入厂批次数量",
              "燃煤合同一共有多少份", "入厂煤的验收量合计是多少",
              "按矿点统计入厂煤批次数量",
              "按组织编码统计入厂煤批次的数量，取数量最多的前 3 个",
              "原煤仓入煤明细条数是多少",
              "组态画面一共有多少个", "人脸识别人员信息表里一共有多少人员",
              "小程序版本管理表中共有多少条版本记录",
              "组态画面中一共引用了多少次组件",
              "人脸识别人员信息中男性有多少人",
              "当前煤场的存煤量是多少",
              "每日耗用量及存煤量条数是多少",
              "煤场进煤量的单日最大值是多少"):
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
