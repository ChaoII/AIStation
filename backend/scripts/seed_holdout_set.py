"""留出集 v1（holdout-v1）：40 道**从未被调优过**的题。

为什么要它
----------
现有 105 题里 57 道能找到近似 few-shot、4 道原题就在示例库、5 道 gold 与指标模板相同、
3 道 gold 事后改过 —— 分数只能当「样本内上限」。留出集的作用是给一个**没被喂过**的数。

选题纪律（写死在这里，后续不许破）
----------------------------------
1. 只用**没被污染**的表：不出现在任何 gold_sql / 指标 sql_template / few-shot sql 里，
   也不是 `seed_*` 脚本造过数据的表（数据是副本库自带的真实行）。
2. 题目**不进 few-shot**、不建指标、不加术语；跑之前冻结规则/指标/术语。
3. 跑完**不许按错题反改**（改了就又变成样本内）。要修只能修「通用缺陷」，
   且必须用别的表验证，不能针对这几道题改。
4. 金标一律带 `ISDELETED = false`（问「已删除」的除外），与平台软删口径一致。

用法
----
    # 1) 只校验金标（不落库）：看每道题返回什么，避免把空结果/全零当金标
    uv run python scripts/seed_holdout_set.py --check
    # 2) 落库（幂等：按 (datasource, question) upsert）
    uv run python scripts/seed_holdout_set.py --apply

落库后评测：`run_eval_once.py --dataset=holdout-v1`，或
`scripts/eval_fair.py --dataset=holdout-v1`（公平口径 + 留出集）。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DS = "ds:6"
DATASET = "holdout-v1"

#: (问题, 金标 SQL, 难度, 题型)
V1_CASES: list[tuple[str, str, str, str]] = [
    # ---- 站点（FUEL_CMCS_STATION）----
    ("站点一共有多少个？",
     'SELECT COUNT(*) AS "站点数" FROM "FUEL_CMCS_STATION" WHERE "ISDELETED" = false', "简单", "计数"),
    ("站点名称去重后有多少个？",
     'SELECT COUNT(DISTINCT "NAME") AS "站点名称数" FROM "FUEL_CMCS_STATION" '
     'WHERE "ISDELETED" = false', "中等", "去重"),
    ("站点里父级为空的顶级站点有多少个？",
     'SELECT COUNT(*) AS "顶级站点数" FROM "FUEL_CMCS_STATION" '
     'WHERE "ISDELETED" = false AND ("PARENTID" IS NULL OR "PARENTID" = \'\')', "中等", "条件筛选"),
    ("站点按排序号分组统计数量，取数量最多的前 3 个排序号",
     'SELECT "SORT" AS "排序号", COUNT(*) AS "站点数" FROM "FUEL_CMCS_STATION" '
     'WHERE "ISDELETED" = false GROUP BY "SORT" '
     'ORDER BY COUNT(*) DESC, "SORT" ASC LIMIT 3', "中等", "分组聚合"),
    ("站点编码去重后有多少个？",
     'SELECT COUNT(DISTINCT "CODE") AS "站点编码数" FROM "FUEL_CMCS_STATION" '
     'WHERE "ISDELETED" = false', "简单", "去重"),

    # ---- 化验审核建议（FUEL_CMCS_ASSAYCHECKSUGGESTION）----
    ("化验审核建议一共有多少条？",
     'SELECT COUNT(*) AS "审核建议数" FROM "FUEL_CMCS_ASSAYCHECKSUGGESTION"', "简单", "计数"),
    ("化验审核建议按活动名称统计条数，最多的是哪个活动、多少条？",
     'SELECT "ACTIVITYNAME" AS "活动名称", COUNT(*) AS "条数" FROM "FUEL_CMCS_ASSAYCHECKSUGGESTION" '
     'GROUP BY "ACTIVITYNAME" ORDER BY COUNT(*) DESC, "ACTIVITYNAME" ASC LIMIT 1', "中等", "分组聚合"),
    ("化验审核建议里 CHECKSTATE 等于 1 的有多少条？",
     'SELECT COUNT(*) AS "条数" FROM "FUEL_CMCS_ASSAYCHECKSUGGESTION" WHERE "CHECKSTATE" = 1',
     "简单", "条件筛选"),
    ("化验审核建议按提交人统计条数，取最多的前 3 人",
     'SELECT "USERNMAE" AS "提交人", COUNT(*) AS "条数" FROM "FUEL_CMCS_ASSAYCHECKSUGGESTION" '
     'GROUP BY "USERNMAE" ORDER BY COUNT(*) DESC, "USERNMAE" ASC LIMIT 3', "中等", "分组聚合"),
    ("最近一条化验审核建议是哪天创建的？",
     'SELECT MAX("CREATIONTIME") AS "最近创建时间" FROM "FUEL_CMCS_ASSAYCHECKSUGGESTION"',
     "简单", "时间窗口"),

    # ---- 装车计划明细（FUEL_MIX_LOADPLANDETAIL）----
    ("装车计划明细一共有多少条？",
     'SELECT COUNT(*) AS "明细数" FROM "FUEL_MIX_LOADPLANDETAIL" WHERE "ISDELETED" = false',
     "简单", "计数"),
    ("装车计划明细的 RUNPLAN 合计是多少？",
     'SELECT SUM("RUNPLAN") AS "RUNPLAN合计" FROM "FUEL_MIX_LOADPLANDETAIL" WHERE "ISDELETED" = false',
     "简单", "求和"),
    ("装车计划明细按 RUNPLAN 分组统计条数，取条数最多的前 3 个值",
     'SELECT "RUNPLAN" AS "RUNPLAN值", COUNT(*) AS "条数" FROM "FUEL_MIX_LOADPLANDETAIL" '
     'WHERE "ISDELETED" = false GROUP BY "RUNPLAN" '
     'ORDER BY COUNT(*) DESC, "RUNPLAN" ASC LIMIT 3', "较难", "分组聚合"),
    ("装车计划明细里 ORDERS 的最大值是多少？",
     'SELECT MAX("ORDERS") AS "ORDERS最大值" FROM "FUEL_MIX_LOADPLANDETAIL" WHERE "ISDELETED" = false',
     "简单", "单维聚合"),

    # ---- 运输计划明细（FUEL_CMCS_TRANSPORTPLANDETAIL）----
    ("运输计划明细一共有多少条？",
     'SELECT COUNT(*) AS "明细数" FROM "FUEL_CMCS_TRANSPORTPLANDETAIL" WHERE "ISDELETED" = false',
     "简单", "计数"),
    ("运输计划明细的 TICKETQTY 合计是多少？",
     'SELECT SUM("TICKETQTY") AS "TICKETQTY合计" FROM "FUEL_CMCS_TRANSPORTPLANDETAIL" '
     'WHERE "ISDELETED" = false', "简单", "求和"),
    ("运输计划明细按发货站点统计条数，取条数最多的前 5 个站点",
     'SELECT "DEPOSITSITENAME" AS "发货站点", COUNT(*) AS "条数" FROM "FUEL_CMCS_TRANSPORTPLANDETAIL" '
     'WHERE "ISDELETED" = false GROUP BY "DEPOSITSITENAME" '
     'ORDER BY COUNT(*) DESC, "DEPOSITSITENAME" ASC LIMIT 5', "中等", "分组聚合"),
    ("运输计划明细的 STOWAGEQTY 合计是多少？",
     'SELECT SUM("STOWAGEQTY") AS "STOWAGEQTY合计" FROM "FUEL_CMCS_TRANSPORTPLANDETAIL" '
     'WHERE "ISDELETED" = false', "简单", "求和"),
    ("运输计划明细里已入厂（INFACTORYTIME 不为空）的有多少条？",
     'SELECT COUNT(*) AS "条数" FROM "FUEL_CMCS_TRANSPORTPLANDETAIL" '
     'WHERE "ISDELETED" = false AND "INFACTORYTIME" IS NOT NULL', "简单", "条件筛选"),
    ("运输计划明细涉及多少个不同的运输计划主表记录？",
     'SELECT COUNT(DISTINCT "MAINID") AS "计划数" FROM "FUEL_CMCS_TRANSPORTPLANDETAIL" '
     'WHERE "ISDELETED" = false', "中等", "去重"),

    # ---- 采购计划明细（FUEL_CMCS_PURCHASEPLANDETAIL）----
    ("采购计划明细一共有多少条？",
     'SELECT COUNT(*) AS "明细数" FROM "FUEL_CMCS_PURCHASEPLANDETAIL" WHERE "ISDELETED" = false',
     "简单", "计数"),
    ("采购计划明细的 PLANQTY 合计是多少？",
     'SELECT SUM("PLANQTY") AS "PLANQTY合计" FROM "FUEL_CMCS_PURCHASEPLANDETAIL" '
     'WHERE "ISDELETED" = false', "简单", "求和"),
    ("采购计划明细的平均完成率是多少？",
     'SELECT AVG("COMPLETIONRATE") AS "平均完成率" FROM "FUEL_CMCS_PURCHASEPLANDETAIL" '
     'WHERE "ISDELETED" = false', "中等", "单维聚合"),
    ("采购计划明细按采购类型统计 PLANQTY 合计，取合计最大的前 3 个类型",
     'SELECT "PURCHASETYPE" AS "采购类型", SUM("PLANQTY") AS "PLANQTY合计" '
     'FROM "FUEL_CMCS_PURCHASEPLANDETAIL" WHERE "ISDELETED" = false '
     'GROUP BY "PURCHASETYPE" ORDER BY SUM("PLANQTY") DESC NULLS LAST, "PURCHASETYPE" ASC LIMIT 3',
     "较难", "分组聚合"),
    ("采购计划明细里完成率大于 1 的有多少条？",
     'SELECT COUNT(*) AS "条数" FROM "FUEL_CMCS_PURCHASEPLANDETAIL" '
     'WHERE "ISDELETED" = false AND "COMPLETIONRATE" > 1', "中等", "条件筛选"),

    # ---- 燃料存储区（FUEL_STG_FUELSTORAGEAREA）----
    ("燃料存储区一共有多少个？",
     'SELECT COUNT(*) AS "存储区数" FROM "FUEL_STG_FUELSTORAGEAREA" WHERE "ISDELETED" = false',
     "简单", "计数"),
    ("燃料存储区的 STARTPOINT 合计是多少？",
     'SELECT SUM("STARTPOINT") AS "STARTPOINT合计" FROM "FUEL_STG_FUELSTORAGEAREA" '
     'WHERE "ISDELETED" = false', "简单", "求和"),
    ("燃料存储区的 ENDPOINT 最大值是多少？",
     'SELECT MAX("ENDPOINT") AS "ENDPOINT最大值" FROM "FUEL_STG_FUELSTORAGEAREA" '
     'WHERE "ISDELETED" = false', "简单", "单维聚合"),
    ("存储区涉及多少个不同的区域编码？",
     'SELECT COUNT(DISTINCT "AREACODE") AS "区域编码数" FROM "FUEL_STG_FUELSTORAGEAREA" '
     'WHERE "ISDELETED" = false', "中等", "去重"),

    # ---- 煤仓实时（FUEL_MIX_BUNKERREALTIME）----
    ("煤仓实时数据里涉及多少个不同的机组？",
     'SELECT COUNT(DISTINCT "GENSETNAME") AS "机组数" FROM "FUEL_MIX_BUNKERREALTIME"', "中等", "去重"),
    ("煤仓实时数据按机组统计煤仓数量，哪个机组的煤仓最多、多少个？",
     'SELECT "GENSETNAME" AS "机组", COUNT(*) AS "煤仓数" FROM "FUEL_MIX_BUNKERREALTIME" '
     'GROUP BY "GENSETNAME" ORDER BY COUNT(*) DESC, "GENSETNAME" ASC LIMIT 1', "中等", "分组聚合"),
    ("煤仓实时数据里 REALH 的平均值是多少？",
     'SELECT AVG("REALH") AS "REALH平均值" FROM "FUEL_MIX_BUNKERREALTIME"', "简单", "单维聚合"),
    ("煤仓实时数据里 SPEED 大于 0 的记录有多少条？",
     'SELECT COUNT(*) AS "条数" FROM "FUEL_MIX_BUNKERREALTIME" WHERE "SPEED" > 0', "简单", "条件筛选"),

    # ---- 运输计划（FUEL_CMCS_TRANSPORTPLAN）----
    ("运输计划一共有多少条？",
     'SELECT COUNT(*) AS "计划数" FROM "FUEL_CMCS_TRANSPORTPLAN" WHERE "ISDELETED" = false',
     "简单", "计数"),
    ("运输计划的 COALQTY 合计是多少？",
     'SELECT SUM("COALQTY") AS "COALQTY合计" FROM "FUEL_CMCS_TRANSPORTPLAN" WHERE "ISDELETED" = false',
     "简单", "求和"),
    ("运输计划里计划时间最早和最晚分别是哪天？",
     'SELECT MIN("PLANTIME") AS "最早计划时间", MAX("PLANTIME") AS "最晚计划时间" '
     'FROM "FUEL_CMCS_TRANSPORTPLAN" WHERE "ISDELETED" = false', "中等", "时间窗口"),
    ("运输计划里车数最多的计划号是哪个、多少车？",
     'SELECT "PLANNUM" AS "计划号", "CARCOUNTS" AS "车数" FROM "FUEL_CMCS_TRANSPORTPLAN" '
     'WHERE "ISDELETED" = false AND "CARCOUNTS" IS NOT NULL '
     'ORDER BY "CARCOUNTS" DESC, "PLANNUM" ASC LIMIT 1', "较难", "排序"),
    ("运输计划的平均煤量（COALQTY）是多少？",
     'SELECT AVG("COALQTY") AS "平均煤量" FROM "FUEL_CMCS_TRANSPORTPLAN" WHERE "ISDELETED" = false',
     "中等", "单维聚合"),

    # ---- 皮带型号（FUEL_CMCS_BELTMODEL）----
    ("皮带型号一共有多少种？",
     'SELECT COUNT(*) AS "型号数" FROM "FUEL_CMCS_BELTMODEL"', "简单", "计数"),
    ("皮带型号按皮带统计数量，取数量最多的前 3 条皮带",
     'SELECT "BELTID" AS "皮带", COUNT(*) AS "型号数" FROM "FUEL_CMCS_BELTMODEL" '
     'GROUP BY "BELTID" ORDER BY COUNT(*) DESC, "BELTID" ASC LIMIT 3', "中等", "分组聚合"),
    ("皮带型号描述里包含 2A 的有多少个？",
     'SELECT COUNT(*) AS "型号数" FROM "FUEL_CMCS_BELTMODEL" '
     'WHERE "MODELDESCRIPTION" LIKE \'%2A%\'', "简单", "条件筛选"),

    # ---- 变更历史（FUEL_STG_CONTROLLOG_CHANGEHISTORY）----
    ("控制日志变更历史一共有多少条？",
     'SELECT COUNT(*) AS "变更数" FROM "FUEL_STG_CONTROLLOG_CHANGEHISTORY"', "简单", "计数"),
    ("变更历史里 CHANGETYPE 等于 3 的有多少条？",
     'SELECT COUNT(*) AS "条数" FROM "FUEL_STG_CONTROLLOG_CHANGEHISTORY" WHERE "CHANGETYPE" = 3',
     "简单", "条件筛选"),
    ("变更历史按属性统计改动次数，取最多的前 3 个属性",
     'SELECT "PROPERTYNAME" AS "属性", COUNT(*) AS "次数" FROM "FUEL_STG_CONTROLLOG_CHANGEHISTORY" '
     'WHERE "PROPERTYNAME" IS NOT NULL '
     'GROUP BY "PROPERTYNAME" ORDER BY COUNT(*) DESC, "PROPERTYNAME" ASC LIMIT 3', "中等", "分组聚合"),
    ("变更历史里原始值为空的记录有多少条？",
     'SELECT COUNT(*) AS "条数" FROM "FUEL_STG_CONTROLLOG_CHANGEHISTORY" '
     'WHERE "ORIGINALVALUE" IS NULL', "简单", "条件筛选"),

    # ---- 日计划信息（FUEL_STG_DAYCOALINFO）----
    ("日计划信息表里有多少个不同的计划日期？",
     'SELECT COUNT(DISTINCT "PLANDATE") AS "计划日期数" FROM "FUEL_STG_DAYCOALINFO" '
     'WHERE "ISDELETED" = false', "中等", "去重"),
    ("日计划信息表里计划日期最早和最晚分别是哪天？",
     'SELECT MIN("PLANDATE") AS "最早日期", MAX("PLANDATE") AS "最晚日期" FROM "FUEL_STG_DAYCOALINFO" '
     'WHERE "ISDELETED" = false', "简单", "时间窗口"),
]


#: v2：换一批**从没被题目/示例/指标用过**的表（v1 的 11 张已「看过」，不能再用）。
#: 这些表都很小（2~29 行），所以题目偏「口径 + 关联 + 空值」而不是「大数据量聚合」。
#: 目的不是再刷一个漂亮分数，而是检验 A/B：描述注入有没有用。
V2_CASES: list[tuple[str, str, str, str]] = [
    # ---- 库存调账（FUEL_STG_FUELADJUSTMENT，23 行/有效 20）----
    ("库存调账记录一共有多少条？",
     'SELECT COUNT(*) AS "调账记录数" FROM "FUEL_STG_FUELADJUSTMENT" WHERE "ISDELETED" = false',
     "简单", "计数"),
    ("库存调账的调账量合计是多少？",
     'SELECT SUM("ADJUSTSTOCKS") AS "调账量合计" FROM "FUEL_STG_FUELADJUSTMENT" '
     'WHERE "ISDELETED" = false', "简单", "求和"),
    ("库存调账里调账量为负的记录有多少条？",
     'SELECT COUNT(*) AS "条数" FROM "FUEL_STG_FUELADJUSTMENT" '
     'WHERE "ISDELETED" = false AND "ADJUSTSTOCKS" < 0', "简单", "条件筛选"),
    ("库存调账里调账后库存的最大值是多少？",
     'SELECT MAX("ADJUST_AFTERSTOCKS") AS "调账后库存最大值" FROM "FUEL_STG_FUELADJUSTMENT" '
     'WHERE "ISDELETED" = false', "简单", "单维聚合"),
    ("库存调账按单据号统计条数，取条数最多的前 3 个单据号",
     'SELECT "BILLNUMBER" AS "单据号", COUNT(*) AS "条数" FROM "FUEL_STG_FUELADJUSTMENT" '
     'WHERE "ISDELETED" = false GROUP BY "BILLNUMBER" '
     'ORDER BY COUNT(*) DESC, "BILLNUMBER" ASC LIMIT 3', "中等", "分组聚合"),

    # ---- 期初库存明细（FUEL_STG_STORAGEINITIALIZEDETAIL，20 行）----
    ("期初库存明细一共有多少条？",
     'SELECT COUNT(*) AS "明细数" FROM "FUEL_STG_STORAGEINITIALIZEDETAIL" WHERE "ISDELETED" = false',
     "简单", "计数"),
    ("期初库存明细的库存量（QTY）合计是多少？",
     'SELECT SUM("QTY") AS "库存量合计" FROM "FUEL_STG_STORAGEINITIALIZEDETAIL" '
     'WHERE "ISDELETED" = false', "简单", "求和"),
    ("期初库存明细的平均收到基低位发热量（QCAL）是多少？",
     'SELECT AVG("QCAL") AS "平均发热量" FROM "FUEL_STG_STORAGEINITIALIZEDETAIL" '
     'WHERE "ISDELETED" = false', "简单", "单维聚合"),
    ("期初库存明细里发热量最高的那条库存量是多少？",
     'SELECT "QTY" AS "库存量" FROM "FUEL_STG_STORAGEINITIALIZEDETAIL" '
     'WHERE "ISDELETED" = false AND "QCAL" IS NOT NULL '
     'ORDER BY "QCAL" DESC, "ID" ASC LIMIT 1', "较难", "排序"),
    ("期初库存明细涉及多少个不同的燃料存储区？",
     'SELECT COUNT(DISTINCT "FUELSTORAGEID") AS "存储区数" FROM "FUEL_STG_STORAGEINITIALIZEDETAIL" '
     'WHERE "ISDELETED" = false', "中等", "去重"),

    # ---- 厂成本年度明细（FUEL_CMCS_FACTORYCOSTYEARDETAIL，29 行/有效 27）----
    ("厂成本年度明细一共有多少条？",
     'SELECT COUNT(*) AS "明细数" FROM "FUEL_CMCS_FACTORYCOSTYEARDETAIL" WHERE "ISDELETED" = false',
     "简单", "计数"),
    ("厂成本年度明细的实际成本合计是多少？",
     'SELECT SUM("REALCOST") AS "实际成本合计" FROM "FUEL_CMCS_FACTORYCOSTYEARDETAIL" '
     'WHERE "ISDELETED" = false', "简单", "求和"),
    ("厂成本年度明细的预算成本合计是多少？",
     'SELECT SUM("BUDGETCOST") AS "预算成本合计" FROM "FUEL_CMCS_FACTORYCOSTYEARDETAIL" '
     'WHERE "ISDELETED" = false', "简单", "求和"),
    ("厂成本年度明细里实际成本超过预算成本的有多少条？",
     'SELECT COUNT(*) AS "条数" FROM "FUEL_CMCS_FACTORYCOSTYEARDETAIL" '
     'WHERE "ISDELETED" = false AND "REALCOST" > "BUDGETCOST"', "中等", "条件筛选"),
    ("厂成本年度明细按成本项目名称统计实际成本合计，取合计最大的前 3 个成本项目",
     'SELECT "POINTNAME" AS "成本项目", SUM("REALCOST") AS "实际成本合计" '
     'FROM "FUEL_CMCS_FACTORYCOSTYEARDETAIL" WHERE "ISDELETED" = false '
     'GROUP BY "POINTNAME" ORDER BY SUM("REALCOST") DESC NULLS LAST, "POINTNAME" ASC LIMIT 3',
     "较难", "分组聚合"),

    # ---- 成本项目（FUEL_CMCS_FACTORYCOSTPOINT，18 行/有效 16）----
    ("成本项目一共有多少个？",
     'SELECT COUNT(*) AS "成本项目数" FROM "FUEL_CMCS_FACTORYCOSTPOINT" WHERE "ISDELETED" = false',
     "简单", "计数"),
    ("成本项目里没有父级的顶级项目有多少个？",
     'SELECT COUNT(*) AS "顶级项目数" FROM "FUEL_CMCS_FACTORYCOSTPOINT" '
     'WHERE "ISDELETED" = false AND ("PARENTID" IS NULL OR "PARENTID" = \'\')', "中等", "条件筛选"),
    ("成本项目按排序号统计数量，取数量最多的前 3 个排序号",
     'SELECT "SORT" AS "排序号", COUNT(*) AS "数量" FROM "FUEL_CMCS_FACTORYCOSTPOINT" '
     'WHERE "ISDELETED" = false GROUP BY "SORT" '
     'ORDER BY COUNT(*) DESC, "SORT" ASC LIMIT 3', "中等", "分组聚合"),

    # ---- 配煤方案分仓（FUEL_MIX_COALSCHEMEBUNKER，8 行）----
    ("配煤方案分仓明细一共有多少条？",
     'SELECT COUNT(*) AS "条数" FROM "FUEL_MIX_COALSCHEMEBUNKER" WHERE "ISDELETED" = false',
     "简单", "计数"),
    ("配煤方案分仓里发热量上限（QCAL_MAX）的最大值是多少？",
     'SELECT MAX("QCAL_MAX") AS "发热量上限最大值" FROM "FUEL_MIX_COALSCHEMEBUNKER" '
     'WHERE "ISDELETED" = false', "简单", "单维聚合"),
    ("配煤方案分仓的全硫上限（ST_MAX）平均值是多少？",
     'SELECT AVG("ST_MAX") AS "全硫上限平均值" FROM "FUEL_MIX_COALSCHEMEBUNKER" '
     'WHERE "ISDELETED" = false', "简单", "单维聚合"),
    ("配煤方案分仓里灰分上限（AD_MAX）大于 20 的有多少条？",
     'SELECT COUNT(*) AS "条数" FROM "FUEL_MIX_COALSCHEMEBUNKER" '
     'WHERE "ISDELETED" = false AND "AD_MAX" > 20', "中等", "条件筛选"),

    # ---- 供应商煤质限制（FUEL_CMCS_SUPPLIERQUALITYLIMIT，7 行）----
    ("供应商煤质限制一共有多少条？",
     'SELECT COUNT(*) AS "条数" FROM "FUEL_CMCS_SUPPLIERQUALITYLIMIT"', "简单", "计数"),
    ("供应商煤质限制涉及多少个不同的供应商？",
     'SELECT COUNT(DISTINCT "SUPPLIERID") AS "供应商数" FROM "FUEL_CMCS_SUPPLIERQUALITYLIMIT"',
     "中等", "去重"),
    ("供应商煤质限制里全水分限制（MTLIMIT）的最大值是多少？",
     'SELECT MAX("MTLIMIT") AS "全水分限制最大值" FROM "FUEL_CMCS_SUPPLIERQUALITYLIMIT"',
     "简单", "单维聚合"),

    # ---- 配煤结果（FUEL_MIX_COALSCHEMERESULT，6 行/有效 3）----
    ("配煤结果一共有多少条？",
     'SELECT COUNT(*) AS "配煤结果数" FROM "FUEL_MIX_COALSCHEMERESULT" WHERE "ISDELETED" = false',
     "简单", "计数"),
    ("配煤结果的混煤量（MIXCOALQ）合计是多少？",
     'SELECT SUM("MIXCOALQ") AS "混煤量合计" FROM "FUEL_MIX_COALSCHEMERESULT" '
     'WHERE "ISDELETED" = false', "简单", "求和"),
    ("配煤结果的平均全硫（MIXCOALS）是多少？",
     'SELECT AVG("MIXCOALS") AS "平均全硫" FROM "FUEL_MIX_COALSCHEMERESULT" '
     'WHERE "ISDELETED" = false', "简单", "单维聚合"),

    # ---- 化验复检（FUEL_CMCS_ASSAYRECHECK，6 行）----
    ("化验复检记录一共有多少条？",
     'SELECT COUNT(*) AS "复检记录数" FROM "FUEL_CMCS_ASSAYRECHECK"', "简单", "计数"),
    ("化验复检记录按复检原因统计条数",
     'SELECT "REASON" AS "复检原因", COUNT(*) AS "条数" FROM "FUEL_CMCS_ASSAYRECHECK" '
     'GROUP BY "REASON" ORDER BY COUNT(*) DESC, "REASON" ASC', "中等", "分组聚合"),
    ("化验复检记录里版本号最大的那条，复检原因是什么？",
     'SELECT "REASON" AS "复检原因" FROM "FUEL_CMCS_ASSAYRECHECK" '
     'ORDER BY "VERSION" DESC, "ID" ASC LIMIT 1', "较难", "排序"),

    # ---- 期初库存主表（FUEL_STG_STORAGEINITIALIZE，6 行）----
    ("期初库存主表一共有多少条记录？",
     'SELECT COUNT(*) AS "记录数" FROM "FUEL_STG_STORAGEINITIALIZE" WHERE "ISDELETED" = false',
     "简单", "计数"),
    ("期初库存主表的记录时间最早和最晚分别是什么时候？",
     'SELECT MIN("RECORDTIME") AS "最早记录时间", MAX("RECORDTIME") AS "最晚记录时间" '
     'FROM "FUEL_STG_STORAGEINITIALIZE" WHERE "ISDELETED" = false', "中等", "时间窗口"),

    # ---- 采购计划主表（FUEL_CMCS_PURCHASEPLAN，5 行/有效 4）----
    ("采购计划主表一共有多少条记录？",
     'SELECT COUNT(*) AS "计划数" FROM "FUEL_CMCS_PURCHASEPLAN" WHERE "ISDELETED" = false',
     "简单", "计数"),
    ("采购计划主表的计划日期最早和最晚分别是哪天？",
     'SELECT MIN("PLANDATE") AS "最早计划日期", MAX("PLANDATE") AS "最晚计划日期" '
     'FROM "FUEL_CMCS_PURCHASEPLAN" WHERE "ISDELETED" = false', "简单", "时间窗口"),

    # ---- 运输方式（FUEL_CMCS_TRANSPORTTYPE，4 行）----
    ("运输方式一共有几种？",
     'SELECT COUNT(*) AS "运输方式数" FROM "FUEL_CMCS_TRANSPORTTYPE" WHERE "ISDELETED" = false',
     "简单", "计数"),
    ("运输方式里名称包含「火」的有几种？",
     'SELECT COUNT(*) AS "运输方式数" FROM "FUEL_CMCS_TRANSPORTTYPE" '
     'WHERE "ISDELETED" = false AND "NAME" LIKE \'%火%\'', "简单", "条件筛选"),
]

SETS: dict[str, list[tuple[str, str, str, str]]] = {
    "holdout-v1": V1_CASES,
    "holdout-v2": V2_CASES,
}


def _auth():
    from types import SimpleNamespace

    return SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))


_BOOTED = False


def _boot() -> None:
    """构造应用一次：ORM mapper 需要全部模型导入后才能初始化（否则报 UserModel 定位失败）。"""
    global _BOOTED
    if _BOOTED:
        return
    from main import create_app

    create_app()
    _BOOTED = True


async def _run_gold(sql: str) -> dict:
    from app.plugin.module_ai.query.execution import _execute_custom_ds_sql

    return await _execute_custom_ds_sql(6, sql, _auth())


async def _check(dataset: str) -> None:
    _boot()
    cases = SETS[dataset]
    print(f"[check] {dataset} 共 {len(cases)} 道题，逐条执行金标（看是否空结果/全空值）")
    bad = 0
    for i, (q, sql, _diff, _form) in enumerate(cases, 1):
        try:
            res = await _run_gold(sql)
            rows = res.get("rows") or []
            cells = [c for r in rows for c in r]
            all_null = bool(cells) and all(c is None for c in cells)
            if not rows or all_null:
                bad += 1
                print(f"BAD  {i:02d} {q} -> rows={rows}")
            else:
                preview = str(rows)[:110]
                print(f"OK   {i:02d} {q} -> {preview}")
        except Exception as e:  # noqa: BLE001
            bad += 1
            print(f"ERR  {i:02d} {q} -> {type(e).__name__}: {str(e)[:120]}")
    print(f"[check] 有问题 {bad} 条 / {len(cases)}")
    if bad:
        sys.exit(1)


async def _apply(dataset: str) -> None:
    _boot()
    cases = SETS[dataset]
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.eval_set import list_cases, upsert_case

    for q, sql, diff, form in cases:
        await upsert_case({
            "question": q, "gold_sql": sql, "datasource": DS,
            "difficulty": diff, "scenario": "留出集", "form": form,
            "tags": ["holdout", "frozen"], "verified": True, "enabled": True,
            "dataset": dataset, "notes": "留出集：跑前冻结，不得据此调优",
        })
    n = len(await list_cases(datasource=DS, dataset=dataset, enabled=True))

    # 冻结校验（真正有意义的口径）：
    #   ① 题目原文不得出现在 few-shot；
    #   ② few-shot 的**示例 SQL 不得用到留出集的表** —— 那才是"看过同一张表怎么问"的真泄漏。
    # 不要用「问句相似度」判：这些题都是「X 一共有多少条」这类通用句式，跟别的计数题天然相似，
    # 用相似度判会把正常题全标红（实测 16/47 误报）。
    import re as _re

    def _tables(sql: str) -> set[str]:
        # 只取 FROM / JOIN 后面的标识符：列名、别名同样带引号，混进来会大量误报
        return {m.group(1).upper()
                for m in _re.finditer(r'(?:FROM|JOIN)\s+"([A-Za-z0-9_]+)"', sql or "", _re.I)}

    async with async_db_session() as db:
        few = (await db.execute(text(
            "SELECT question, sql FROM ai_query_fewshot WHERE datasource=:d AND is_deleted=false"
        ), {"d": DS})).fetchall()
    exact = [q for q, *_ in cases if any(str(f[0]) == q for f in few)]
    table_leak = []
    for q, sql, *_ in cases:
        mine = _tables(sql)
        hit = [f[0] for f in few if mine & _tables(str(f[1] or ""))]
        if hit:
            table_leak.append((q, hit[:2]))
    h = hashlib.sha1("\n".join(sorted(q for q, *_ in cases)).encode("utf-8")).hexdigest()[:16]
    print(f"[ok] {dataset} 已落库 {n} 条；题目指纹 {h}")
    print(f"[ok] 泄漏检查：原题命中 {len(exact)} 条；示例 SQL 用到留出集表 {len(table_leak)} 条")
    for q, hit in table_leak[:5]:
        print(f"     - {q} :: {hit}")
    if exact or table_leak:
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="holdout-v1", choices=sorted(SETS))
    ap.add_argument("--check", action="store_true", help="只校验金标，不落库")
    ap.add_argument("--apply", action="store_true", help="落库（幂等）")
    args = ap.parse_args()
    if args.check:
        asyncio.run(_check(args.dataset))
    elif args.apply:
        asyncio.run(_apply(args.dataset))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
