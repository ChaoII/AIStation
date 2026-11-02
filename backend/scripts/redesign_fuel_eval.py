"""题库重设计：先审计旧题（金标能不能跑出数据），再落一套**数据可验证**的新题。

为什么要重做
------------
旧题库有两个致命问题（都是实测出来的）：

1. **金标跑不出数据**：问「运损合计是多少」，而 ``FUEL_CMCS_INFACTORYBATCH.RAILLOST``
   全表合计 = 0；问时间窗口，而数据只到 2026-09；问化验方式，而 ``ASSAYWAY``
   2527 行里 2521 行是 NULL。这种题**永远评不出东西**，还会把消融的 delta 压成 0。
2. **题目太同质**：多半是"数某张表有多少条"，关掉召回/语义/工具照样答对 ——
   消融所以全是 +0.000。

做法
----
- 审计：逐题执行金标，分成 OK / EMPTY（0 行或全空）/ ERROR（语法或列不存在）；
- 只保留能跑出数据的题（自动停用另外两类，附原因）；
- 新题分 8 类（条件筛选、分组聚合、多表联查、去重、求和平均、排序取前 N、
  时间窗口、占比），每题都在真实数据上验证过非空。

用法::

    cd backend
    uv run python scripts/redesign_fuel_eval.py --audit          # 只看旧题体检结果
    uv run python scripts/redesign_fuel_eval.py --seed           # 落新题库（先验证）
    uv run python scripts/redesign_fuel_eval.py --apply          # 真正写库
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from app.core.database import async_db_session
from app.plugin.module_ai.query import executor as _ex

DS = "ds:4"
NEW_DATASET = "fuel-v2"

#: 新题库：每条都在真实数据上验证过（验证不过的会被自动剔除并打印原因）
CASES: list[dict] = [
    # ---- A. 单表计数（快路径应命中）----
    {"cat": "计数", "q": "入厂煤化验单一共有多少条？",
     "gold": "SELECT COUNT(*) AS 化验单数 FROM \"FUEL_CMCS_ASSAY\""},
    {"cat": "计数", "q": "矿点一共有多少个？",
     "gold": "SELECT COUNT(*) AS 矿点数 FROM \"FUEL_CMCS_MINE\""},
    {"cat": "计数", "q": "煤种一共有多少种？",
     "gold": "SELECT COUNT(*) AS 煤种数 FROM \"FUEL_CMCS_FUELKIND\""},
    {"cat": "计数", "q": "供应商矿点关系一共有多少条？",
     "gold": "SELECT COUNT(*) AS 关系数 FROM \"DTXY_GYSKDGX\""},
    {"cat": "计数", "q": "煤场进煤记录有多少条？",
     "gold": "SELECT COUNT(*) AS 进煤记录数 FROM \"FUEL_STG_ALLINMIDDLE\""},

    # ---- B. 条件筛选（模板答不了，必须 NL2SQL）----
    {"cat": "条件筛选", "q": "化验单备注里有多少条包含自动生成？",
     "gold": "SELECT COUNT(*) AS 含自动生成的化验单数 FROM \"FUEL_CMCS_ASSAY\" "
             "WHERE \"REMARK\" LIKE '%自动生成%'"},
    {"cat": "条件筛选", "q": "已删除的入厂煤批次有多少条？",
     "gold": "SELECT COUNT(*) AS 已删除批次数 FROM \"FUEL_CMCS_INFACTORYBATCH\" "
             "WHERE \"ISDELETED\" = true"},
    {"cat": "条件筛选", "q": "矿点名称里带“煤”字的有多少个？",
     "gold": "SELECT COUNT(*) AS 含煤字的矿点数 FROM \"FUEL_CMCS_MINE\" WHERE \"NAME\" LIKE '%煤%'"},
    {"cat": "条件筛选", "q": "化验日期在 2026 年 9 月的化验单有多少条？",
     "gold": "SELECT COUNT(*) AS 九月化验单数 FROM \"FUEL_CMCS_ASSAY\" "
             "WHERE \"ASSAYDATE\" >= '2026-09-01' AND \"ASSAYDATE\" < '2026-10-01'"},
    {"cat": "条件筛选", "q": "化验单里备注不为空的有多少条？",
     "gold": "SELECT COUNT(*) AS 有备注的化验单数 FROM \"FUEL_CMCS_ASSAY\" "
             "WHERE \"REMARK\" IS NOT NULL AND trim(\"REMARK\") <> ''"},
    {"cat": "条件筛选", "q": "2026 年 3 月有多少条化验单？",
     "gold": "SELECT COUNT(*) AS 三月化验单数 FROM \"FUEL_CMCS_ASSAY\" "
             "WHERE \"ASSAYDATE\" >= '2026-03-01' AND \"ASSAYDATE\" < '2026-04-01'"},
    {"cat": "条件筛选", "q": "矿点名称以“煤”字开头的矿点有多少个？",
     "gold": "SELECT COUNT(*) AS 煤字开头的矿点数 FROM \"FUEL_CMCS_MINE\" WHERE \"NAME\" LIKE '煤%'"},
    {"cat": "条件筛选", "q": "关联矿点数超过 2 个的供应商有多少家？",
     "gold": "SELECT COUNT(*) AS 供应商数 FROM (SELECT \"GYSNAME\" FROM \"DTXY_GYSKDGX\" "
             "GROUP BY \"GYSNAME\" HAVING COUNT(*) > 2) x"},

    # ---- C. 分组聚合（单值指标答不了）----
    {"cat": "分组聚合", "q": "按煤种统计平均收到基低位发热量",
     "gold": "SELECT \"COALTYPE\" AS 煤种, ROUND(AVG(CAST(\"RZ\" AS numeric))::numeric, 2) AS 平均发热量 "
             "FROM \"DTXY_PMXX\" WHERE \"RZ\" IS NOT NULL GROUP BY \"COALTYPE\" ORDER BY 煤种"},
    # 注意：库注释里 LF=干基全硫、QSF=全水分。最早我把这条写成 AVG(LF)，是**金标写错**，
    # 模型答 QSF 反而是对的 —— 评测把金标错误抓了出来。
    {"cat": "分组聚合", "q": "按煤种统计平均全水分",
     "gold": "SELECT \"COALTYPE\" AS 煤种, ROUND(AVG(CAST(\"QSF\" AS numeric))::numeric, 3) AS 平均全水分 "
             "FROM \"DTXY_PMXX\" WHERE \"QSF\" IS NOT NULL GROUP BY \"COALTYPE\" ORDER BY 煤种"},
    {"cat": "分组聚合", "q": "按组织编码统计入厂煤批次的数量，取数量最多的前 3 个",
     "gold": "SELECT \"ORGANIZATIONCODE\" AS 组织编码, COUNT(*) AS 批次数 "
             "FROM \"FUEL_CMCS_INFACTORYBATCH\" WHERE \"ORGANIZATIONCODE\" IS NOT NULL "
             "GROUP BY 1 ORDER BY 批次数 DESC, 组织编码 LIMIT 3"},
    {"cat": "分组聚合", "q": "化验日期不为空的化验单按月份统计条数，取数量最多的前 3 个月",
     "gold": "SELECT to_char(\"ASSAYDATE\", 'YYYY-MM') AS 月份, COUNT(*) AS 化验单数 "
             "FROM \"FUEL_CMCS_ASSAY\" WHERE \"ASSAYDATE\" IS NOT NULL "
             "GROUP BY 1 ORDER BY 化验单数 DESC, 月份 LIMIT 3"},
    {"cat": "分组聚合", "q": "煤场进煤记录按操作类型统计条数，取最多的前 3 类",
     "gold": "SELECT \"OPERTYPE\" AS 操作类型, COUNT(*) AS 记录数 FROM \"FUEL_STG_ALLINMIDDLE\" "
             "WHERE \"OPERTYPE\" IS NOT NULL GROUP BY 1 ORDER BY 记录数 DESC, 操作类型 LIMIT 3"},

    # ---- D. 多表联查（召回/本体是否带上对表，就见分晓）----
    
    {"cat": "多表联查", "q": "化验单里出现过多少个不同的入厂煤批次？",
     "gold": "SELECT COUNT(DISTINCT \"INFACTORYBATCHID\") AS 批次数 "
             "FROM \"FUEL_CMCS_ASSAY\" WHERE \"ISDELETED\" = false "
             "AND \"INFACTORYBATCHID\" IS NOT NULL"},
    {"cat": "多表联查", "q": "煤场进煤总量减去取煤总量是多少吨？",
     "gold": "SELECT (SELECT SUM(\"QTYIN\") FROM \"FUEL_STG_ALLINMIDDLE\") "
             "- (SELECT SUM(\"QTYOUT\") FROM \"FUEL_STG_ALLOUTMIDDLE\") AS 净入煤量"},
    {"cat": "多表联查", "q": "同一个供应商最多关联了多少个矿点？",
     "gold": "SELECT MAX(c) AS 最多关联矿点数 FROM "
             "(SELECT COUNT(*) AS c FROM \"DTXY_GYSKDGX\" GROUP BY \"GYSNAME\") x"},

    # ---- E. 去重计数 ----
    {"cat": "去重", "q": "供应商矿点关系表里出现过多少家不同的供应商？",
     "gold": "SELECT COUNT(DISTINCT \"GYSNAME\") AS 供应商数 FROM \"DTXY_GYSKDGX\""},
    {"cat": "去重", "q": "一共有多少个不同的矿点出现在供应商矿点关系里？",
     "gold": "SELECT COUNT(DISTINCT \"KDNAME\") AS 矿点数 FROM \"DTXY_GYSKDGX\""},
    {"cat": "去重", "q": "入厂煤批次里一共有多少个不同的矿点？",
     "gold": "SELECT COUNT(DISTINCT \"MINENAME\") AS 矿点数 FROM \"FUEL_CMCS_INFACTORYBATCH\" "
             "WHERE \"MINENAME\" IS NOT NULL"},
    {"cat": "去重", "q": "入厂煤批次里有多少个不重复的批次号？",
     "gold": "SELECT COUNT(DISTINCT \"BATCH\") AS 批次数 FROM \"FUEL_CMCS_INFACTORYBATCH\" "
             "WHERE \"BATCH\" IS NOT NULL"},
    {"cat": "去重", "q": "有多少个不重复的矿点编码？",
     "gold": "SELECT COUNT(DISTINCT \"CODE\") AS 矿点编码数 FROM \"FUEL_CMCS_MINE\" "
             "WHERE \"CODE\" IS NOT NULL"},

    # ---- F. 求和 / 平均 ----
    {"cat": "求和", "q": "煤场进煤总量是多少？",
     "gold": "SELECT ROUND(SUM(\"QTYIN\")::numeric, 2) AS 进煤总量 FROM \"FUEL_STG_ALLINMIDDLE\""},
    {"cat": "求和", "q": "煤场取煤总量是多少？",
     "gold": "SELECT ROUND(SUM(\"QTYOUT\")::numeric, 2) AS 取煤总量 FROM \"FUEL_STG_ALLOUTMIDDLE\""},
    {"cat": "求和", "q": "入厂煤堆放总量是多少？",
     "gold": "SELECT ROUND(SUM(\"TOTALQTY\")::numeric, 2) AS 堆放总量 FROM \"FUEL_STG_DEPOSIT\""},
    {"cat": "求和", "q": "每日耗用量合计是多少？",
     "gold": "SELECT ROUND(SUM(\"TOTALUSEQTY\")::numeric, 2) AS 耗用量合计 "
             "FROM \"FUEL_REPORT_DAYINOUTSTORAGE\""},
    {"cat": "求和", "q": "煤场进煤记录的平均进煤量是多少？",
     "gold": "SELECT ROUND(AVG(\"QTYIN\")::numeric, 2) AS 平均进煤量 FROM \"FUEL_STG_ALLINMIDDLE\""},
    {"cat": "求和", "q": "煤质信息表里收到基低位发热量最高是多少？",
     "gold": "SELECT MAX(CAST(\"RZ\" AS numeric)) AS 最高发热量 FROM \"DTXY_PMXX\" WHERE \"RZ\" IS NOT NULL"},
    {"cat": "求和", "q": "煤质信息表里全水分最低是多少？",
     "gold": "SELECT MIN(CAST(\"QSF\" AS numeric)) AS 最低全水分 FROM \"DTXY_PMXX\" WHERE \"QSF\" IS NOT NULL"},

    # ---- G. 排序 / 前 N / 占比 ----
    {"cat": "排序", "q": "煤场进煤记录里，按记录日期统计进煤量最大的前 5 天？",
     "gold": "SELECT date(\"RECORDDATE\") AS 日期, ROUND(SUM(\"QTYIN\")::numeric, 2) AS 进煤量 "
             "FROM \"FUEL_STG_ALLINMIDDLE\" WHERE \"RECORDDATE\" IS NOT NULL "
             "GROUP BY date(\"RECORDDATE\") ORDER BY 进煤量 DESC LIMIT 5"},
    {"cat": "排序", "q": "取煤记录里取煤量最大的前 5 天是哪些天？",
     "gold": "SELECT date(\"RECORDDATE\") AS 日期, ROUND(SUM(\"QTYOUT\")::numeric, 2) AS 取煤量 "
             "FROM \"FUEL_STG_ALLOUTMIDDLE\" WHERE \"RECORDDATE\" IS NOT NULL "
             "GROUP BY date(\"RECORDDATE\") ORDER BY 取煤量 DESC LIMIT 5"},
    {"cat": "排序", "q": "煤种按编码升序，列出前 5 个煤种名称",
     "gold": "SELECT \"NAME\" AS 煤种名称 FROM \"FUEL_CMCS_FUELKIND\" "
             "WHERE \"NAME\" IS NOT NULL ORDER BY \"CODE\" LIMIT 5"},
    {"cat": "占比", "q": "入厂煤批次里已删除的占百分之多少？",
     "gold": "SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE \"ISDELETED\") / COUNT(*), 2) AS 删除占比 "
             "FROM \"FUEL_CMCS_INFACTORYBATCH\""},
    {"cat": "占比", "q": "关联矿点数最多的那家供应商是谁，它占全部关系的百分之多少？",
     "gold": "SELECT \"GYSNAME\" AS 供应商, ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM \"DTXY_GYSKDGX\"), 2) AS 占比 "
             "FROM \"DTXY_GYSKDGX\" GROUP BY \"GYSNAME\" ORDER BY COUNT(*) DESC LIMIT 1"},

    # ---- H. 时间窗口（锚在数据真实存在的月份上）----
    {"cat": "时间窗口", "q": "2026 年 9 月的入厂煤批次有多少条？",
     "gold": "SELECT COUNT(*) AS 九月批次数 FROM \"FUEL_CMCS_INFACTORYBATCH\" "
             "WHERE \"CREATIONTIME\" >= '2026-09-01' AND \"CREATIONTIME\" < '2026-10-01'"},
    {"cat": "时间窗口", "q": "2026 年 9 月每天有多少条化验单？按日期升序列出",
     "gold": "SELECT date(\"ASSAYDATE\") AS 日期, COUNT(*) AS 化验单数 FROM \"FUEL_CMCS_ASSAY\" "
             "WHERE \"ASSAYDATE\" >= '2026-09-01' AND \"ASSAYDATE\" < '2026-10-01' "
             "GROUP BY date(\"ASSAYDATE\") ORDER BY 日期"},
    {"cat": "时间窗口", "q": "按日期汇总每日耗用量，耗用量合计最大的那天合计是多少？",
     "gold": "SELECT date(\"RECORDDATE\") AS 日期, ROUND(SUM(\"TOTALUSEQTY\")::numeric, 2) AS 耗用量合计 "
             "FROM \"FUEL_REPORT_DAYINOUTSTORAGE\" WHERE \"TOTALUSEQTY\" IS NOT NULL AND \"ISDELETED\" = false "
             "GROUP BY date(\"RECORDDATE\") ORDER BY 耗用量合计 DESC LIMIT 1"},
    # ---- I. 扩充：单表条件 / 极值 / 分组 / 时间（第二、三批）----
    {"cat": "条件筛选", "q": "化验单里已删除的有多少条？",
     "gold": "SELECT COUNT(*) AS 已删除化验单数 FROM \"FUEL_CMCS_ASSAY\" WHERE \"ISDELETED\" = true"},
    {"cat": "条件筛选", "q": "化验单里化验日期为空的有多少条？",
     "gold": "SELECT COUNT(*) AS 化验日期为空数 FROM \"FUEL_CMCS_ASSAY\" WHERE \"ASSAYDATE\" IS NULL"},
    {"cat": "条件筛选", "q": "入厂煤批次里矿点名称为空的有多少条？",
     "gold": "SELECT COUNT(*) AS 矿点为空批次数 FROM \"FUEL_CMCS_INFACTORYBATCH\" "
             "WHERE \"MINENAME\" IS NULL OR trim(\"MINENAME\") = ''"},
    {"cat": "条件筛选", "q": "矿点里编码为空的有多少个？",
     "gold": "SELECT COUNT(*) AS 编码为空的矿点数 FROM \"FUEL_CMCS_MINE\" "
             "WHERE \"CODE\" IS NULL OR trim(\"CODE\") = ''"},
    {"cat": "条件筛选", "q": "煤质信息里全水分大于 10 的记录有多少条？",
     "gold": "SELECT COUNT(*) AS 记录数 FROM \"DTXY_PMXX\" "
             "WHERE CAST(\"QSF\" AS numeric) > 10"},
    {"cat": "条件筛选", "q": "煤质信息里收到基低位发热量小于 3000 的记录有多少条？",
     "gold": "SELECT COUNT(*) AS 记录数 FROM \"DTXY_PMXX\" "
             "WHERE CAST(\"RZ\" AS numeric) < 3000"},
    {"cat": "条件筛选", "q": "堆放信息里堆煤量超过 10000 的记录有多少条？",
     "gold": "SELECT COUNT(*) AS 记录数 FROM \"FUEL_STG_DEPOSIT\" "
             "WHERE CAST(\"TOTALQTY\" AS numeric) > 10000"},
    {"cat": "条件筛选", "q": "每日出入库报表里耗用量为 0 的有多少条？",
     "gold": "SELECT COUNT(*) AS 记录数 FROM \"FUEL_REPORT_DAYINOUTSTORAGE\" "
             "WHERE CAST(\"TOTALUSEQTY\" AS numeric) = 0"},
    {"cat": "条件筛选", "q": "化验单里 2025 年有多少条？",
     "gold": "SELECT COUNT(*) AS 化验单数 FROM \"FUEL_CMCS_ASSAY\" "
             "WHERE \"ASSAYDATE\" >= '2025-01-01' AND \"ASSAYDATE\" < '2026-01-01'"},
    {"cat": "条件筛选", "q": "煤场进煤记录里 2026 年 8 月有多少条？",
     "gold": "SELECT COUNT(*) AS 记录数 FROM \"FUEL_STG_ALLINMIDDLE\" "
             "WHERE \"RECORDDATE\" >= '2026-08-01' AND \"RECORDDATE\" < '2026-09-01'"},

    {"cat": "求和", "q": "煤质信息的平均灰分是多少？",
     "gold": "SELECT ROUND(AVG(CAST(\"HF\" AS numeric))::numeric, 2) AS 平均灰分 "
             "FROM \"DTXY_PMXX\" WHERE \"HF\" IS NOT NULL"},
    {"cat": "求和", "q": "煤质信息的平均干燥无灰基挥发分是多少？",
     "gold": "SELECT ROUND(AVG(CAST(\"HFF\" AS numeric))::numeric, 2) AS 平均挥发分 "
             "FROM \"DTXY_PMXX\" WHERE \"HFF\" IS NOT NULL"},
    {"cat": "求和", "q": "取煤记录一共有多少条？",
     "gold": "SELECT COUNT(*) AS 取煤记录数 FROM \"FUEL_STG_ALLOUTMIDDLE\""},
    {"cat": "求和", "q": "煤场进煤量的单日最大值是多少？",
     "gold": "SELECT ROUND(MAX(d)::numeric, 2) AS 单日最大进煤量 FROM "
             "(SELECT SUM(CAST(\"QTYIN\" AS numeric)) AS d FROM \"FUEL_STG_ALLINMIDDLE\" "
             " GROUP BY date(\"RECORDDATE\")) x"},
    {"cat": "求和", "q": "每日出入库报表一共有多少条记录？",
     "gold": "SELECT COUNT(*) AS 记录数 FROM \"FUEL_REPORT_DAYINOUTSTORAGE\""},
    {"cat": "求和", "q": "煤质信息里一共涉及多少个矿点？",
     "gold": "SELECT COUNT(DISTINCT \"KDID\") AS 矿点数 FROM \"DTXY_PMXX\" "
             "WHERE \"KDID\" IS NOT NULL"},
    {"cat": "求和", "q": "按供应商名称分组，每个供应商平均关联几个矿点？",
     "gold": "SELECT ROUND(AVG(c)::numeric, 2) AS 平均关联矿点数 FROM "
             "(SELECT COUNT(*) AS c FROM \"DTXY_GYSKDGX\" GROUP BY \"GYSNAME\") x"},
    {"cat": "求和", "q": "煤场进煤记录和取煤记录加起来一共多少条？",
     "gold": "SELECT (SELECT COUNT(*) FROM \"FUEL_STG_ALLINMIDDLE\") "
             "+ (SELECT COUNT(*) FROM \"FUEL_STG_ALLOUTMIDDLE\") AS 记录总数"},
    {"cat": "求和", "q": "化验单里化验日期最早和最晚分别是哪天？",
     "gold": "SELECT MIN(\"ASSAYDATE\") AS 最早化验日期, MAX(\"ASSAYDATE\") AS 最晚化验日期 "
             "FROM \"FUEL_CMCS_ASSAY\""},
    {"cat": "求和", "q": "煤场进煤记录最早和最晚的记录日期分别是哪天？",
     "gold": "SELECT MIN(\"RECORDDATE\") AS 最早日期, MAX(\"RECORDDATE\") AS 最晚日期 "
             "FROM \"FUEL_STG_ALLINMIDDLE\""},

    {"cat": "去重", "q": "矿点名称去重后有多少个？",
     "gold": "SELECT COUNT(DISTINCT \"NAME\") AS 矿点数 FROM \"FUEL_CMCS_MINE\" "
             "WHERE \"NAME\" IS NOT NULL"},
    {"cat": "去重", "q": "煤种名称去重后有多少个？",
     "gold": "SELECT COUNT(DISTINCT \"NAME\") AS 煤种数 FROM \"FUEL_CMCS_FUELKIND\" "
             "WHERE \"NAME\" IS NOT NULL"},
    {"cat": "去重", "q": "煤质信息里一共有几种煤种类型？",
     "gold": "SELECT COUNT(DISTINCT \"COALTYPE\") AS 煤种类型数 FROM \"DTXY_PMXX\" "
             "WHERE \"COALTYPE\" IS NOT NULL"},

    {"cat": "分组聚合", "q": "化验单按化验方式分组统计条数",
     "gold": "SELECT \"ASSAYWAY\" AS 化验方式, COUNT(*) AS 化验单数 FROM \"FUEL_CMCS_ASSAY\" "
             "GROUP BY \"ASSAYWAY\" ORDER BY 化验单数 DESC"},
    {"cat": "分组聚合", "q": "煤质信息里品名（非空）出现次数最多的前 3 个",
     "gold": "SELECT \"VARIETY\" AS 品名, COUNT(*) AS 记录数 FROM \"DTXY_PMXX\" "
             "WHERE \"VARIETY\" IS NOT NULL AND trim(\"VARIETY\") <> '' "
             "GROUP BY 1 ORDER BY 记录数 DESC, 品名 LIMIT 3"},
    {"cat": "分组聚合", "q": "供应商矿点关系里关联矿点最多的前 3 家供应商及其矿点数",
     "gold": "SELECT \"GYSNAME\" AS 供应商, COUNT(*) AS 矿点数 FROM \"DTXY_GYSKDGX\" "
             "GROUP BY 1 ORDER BY 矿点数 DESC, 供应商 LIMIT 3"},
    {"cat": "分组聚合", "q": "按矿点名称统计不同供应商名称的数量，取最多的前 3 个矿点",
     "gold": "SELECT \"KDNAME\" AS 矿点, COUNT(DISTINCT \"GYSNAME\") AS 供应商数 "
             "FROM \"DTXY_GYSKDGX\" WHERE \"KDNAME\" IS NOT NULL "
             "GROUP BY 1 ORDER BY 供应商数 DESC, 矿点 LIMIT 3"},
    {"cat": "分组聚合", "q": "煤场进煤记录按年月统计条数",
     "gold": "SELECT to_char(\"RECORDDATE\", 'YYYY-MM') AS 年月, COUNT(*) AS 记录数 "
             "FROM \"FUEL_STG_ALLINMIDDLE\" WHERE \"RECORDDATE\" IS NOT NULL "
             "GROUP BY 1 ORDER BY 年月"},
    {"cat": "分组聚合", "q": "每日出入库报表按年月统计耗用量合计，取合计最大的前 3 个月",
     "gold": "SELECT to_char(\"RECORDDATE\", 'YYYY-MM') AS 年月, "
             "ROUND(SUM(CAST(\"TOTALUSEQTY\" AS numeric))::numeric, 2) AS 耗用量合计 "
             "FROM \"FUEL_REPORT_DAYINOUTSTORAGE\" WHERE \"RECORDDATE\" IS NOT NULL "
             "GROUP BY 1 ORDER BY 耗用量合计 DESC, 年月 LIMIT 3"},

    {"cat": "排序", "q": "取煤记录里按日期统计，单日取煤量最大的前 3 天",
     "gold": "SELECT date(\"RECORDDATE\") AS 日期, "
             "ROUND(SUM(CAST(\"QTYOUT\" AS numeric))::numeric, 2) AS 取煤量 "
             "FROM \"FUEL_STG_ALLOUTMIDDLE\" WHERE \"RECORDDATE\" IS NOT NULL "
             "GROUP BY date(\"RECORDDATE\") ORDER BY 取煤量 DESC LIMIT 3"},
    {"cat": "排序", "q": "按收到基低位发热量从高到低排列，发热量相同按煤种升序，取前 3 条的煤种和发热量",
     "gold": "SELECT \"COALTYPE\" AS 煤种, CAST(\"RZ\" AS numeric) AS 发热量 FROM \"DTXY_PMXX\" "
             "WHERE \"RZ\" IS NOT NULL ORDER BY 发热量 DESC, 煤种 LIMIT 3"},
    {"cat": "排序", "q": "取煤记录里 2026 年 8 月的取煤量合计是多少？",
     "gold": "SELECT ROUND(SUM(CAST(\"QTYOUT\" AS numeric))::numeric, 2) AS 取煤量合计 "
             "FROM \"FUEL_STG_ALLOUTMIDDLE\" "
             "WHERE \"RECORDDATE\" >= '2026-08-01' AND \"RECORDDATE\" < '2026-09-01'"},

    {"cat": "占比", "q": "化验单里已删除的占百分之多少？",
     "gold": "SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE \"ISDELETED\") / COUNT(*), 2) AS 删除占比 "
             "FROM \"FUEL_CMCS_ASSAY\""},
    {"cat": "占比", "q": "入厂煤批次里矿点名称既不是空字符串也不是 NULL 的占比是多少？",
     "gold": "SELECT ROUND(100.0 * COUNT(*) FILTER "
             "(WHERE \"MINENAME\" IS NOT NULL AND trim(\"MINENAME\") <> '') / COUNT(*), 2) AS 占比 "
             "FROM \"FUEL_CMCS_INFACTORYBATCH\""},
    {"cat": "时间窗口", "q": "煤质信息里 2026 年的记录有多少条？",
     "gold": "SELECT COUNT(*) AS 记录数 FROM \"DTXY_PMXX\" "
             "WHERE \"CREATIONTIME\" >= '2026-01-01' AND \"CREATIONTIME\" < '2027-01-01'"},
    {"cat": "时间窗口", "q": "入厂煤批次按创建时间统计，2026 年 9 月每天有多少条？按日期升序列出",
     "gold": "SELECT date(\"CREATIONTIME\") AS 日期, COUNT(*) AS 批次数 "
             "FROM \"FUEL_CMCS_INFACTORYBATCH\" "
             "WHERE \"CREATIONTIME\" >= '2026-09-01' AND \"CREATIONTIME\" < '2026-10-01' "
             "GROUP BY date(\"CREATIONTIME\") ORDER BY 日期"},
    {"cat": "时间窗口", "q": "煤场进煤记录里 2026 年 8 月的进煤量合计是多少？",
     "gold": "SELECT ROUND(SUM(CAST(\"QTYIN\" AS numeric))::numeric, 2) AS 进煤量合计 "
             "FROM \"FUEL_STG_ALLINMIDDLE\" "
             "WHERE \"RECORDDATE\" >= '2026-08-01' AND \"RECORDDATE\" < '2026-09-01'"},
    {"cat": "多表联查", "q": "煤场进煤记录比取煤记录多多少条？",
     "gold": "SELECT (SELECT COUNT(*) FROM \"FUEL_STG_ALLINMIDDLE\") "
             "- (SELECT COUNT(*) FROM \"FUEL_STG_ALLOUTMIDDLE\") AS 记录数差"},
    
]


async def _cfg() -> dict:
    async with async_db_session() as db:
        r = (await db.execute(text(
            "SELECT type,host,port,database,username,password FROM ai_query_datasources "
            "WHERE is_deleted=false AND id=4"))).fetchone()
    return {"type": r[0], "host": r[1], "port": r[2], "database": r[3],
            "username": r[4], "password": r[5]}


async def _classify(cfg: dict, sql: str) -> tuple[str, str]:
    """返回 (状态, 说明)：OK / EMPTY / ERROR。"""
    if not (sql or "").strip():
        return "EMPTY", "无金标 SQL"
    try:
        out = await _ex.execute_select(cfg, sql)
    except Exception as e:  # noqa: BLE001
        return "ERROR", str(e).split("\n")[0][:120]
    rows = out.get("rows") or []
    if not rows:
        return "EMPTY", "返回 0 行"
    if all(all(v is None for v in r) for r in rows):
        return "EMPTY", "全部为 NULL"
    return "OK", f"{len(rows)} 行"


async def _audit(cfg: dict) -> tuple[list, list]:
    async with async_db_session() as db:
        cases = (await db.execute(text(
            "SELECT id, question, gold_sql, dataset, datasource FROM ai_query_testcase "
            "WHERE is_deleted=false ORDER BY id"))).fetchall()
    ok, bad = [], []
    for cid, q, gold, dataset, ds in cases:
        if (ds or "") != DS:
            continue          # 只审计 ds:4 的题（其它数据源连不上就全判错，没意义）
        state, why = await _classify(cfg, gold or "")
        (ok if state == "OK" else bad).append((cid, q, dataset, state, why))
    return ok, bad


async def main() -> None:  # pragma: no cover - 运维脚本
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    cfg = await _cfg()

    if args.audit or args.apply:
        ok, bad = await _audit(cfg)
        print(f"审计 ds:4 题：可用 {len(ok)}，不可用 {len(bad)}\n")
        for cid, q, dataset, state, why in bad[:30]:
            print(f"  [{state}] #{cid} ({dataset}) {q[:32]} —— {why}")
        if len(bad) > 30:
            print(f"  …… 其余 {len(bad) - 30} 条略")
        if args.apply and bad:
            async with async_db_session.begin() as db:
                for cid, _q, _d, state, why in bad:
                    await db.execute(text(
                        "UPDATE ai_query_testcase SET enabled=false, verified=false, "
                        "notes=:n, updated_time=now() WHERE id=:i"),
                        {"n": f"题库整理：{state} —— {why}"[:200], "i": cid})
            print(f"\n已停用 {len(bad)} 道跑不出数据的题")

    if args.seed or args.apply:
        kept, dropped = [], []
        for c in CASES:
            state, why = await _classify(cfg, c["gold"])
            (kept if state == "OK" else dropped).append((c, state, why))
        print(f"\n新题库：通过验证 {len(kept)} / {len(CASES)}")
        for c, state, why in dropped:
            print(f"  [{state}] 剔除：{c['q'][:40]} —— {why}")
        if args.apply and kept:
            async with async_db_session.begin() as db:
                # 先整组关掉：题目文本改过的旧行不会命中 upsert，留着会重复计分
                await db.execute(text(
                    "UPDATE ai_query_testcase SET enabled=false WHERE dataset=:ds "
                    "AND is_deleted=false"), {"ds": NEW_DATASET})
                for c, _s, _w in kept:
                    await db.execute(text(
                        "INSERT INTO ai_query_testcase"
                        "(question,gold_sql,datasource,difficulty,scenario,form,dataset,"
                        " verified,enabled,last_verified_at,is_deleted,created_time,updated_time) "
                        "VALUES (:q,:g,:d,:diff,:sc,'sql',:ds,true,true,now(),false,now(),now()) "
                        "ON CONFLICT (datasource, question) DO UPDATE SET "
                        " gold_sql=:g, dataset=:ds, verified=true, enabled=true, "
                        " scenario=:sc, updated_time=now()"),
                        {"q": c["q"], "g": c["gold"], "d": DS,
                         "diff": c.get("cat", "medium"), "sc": c.get("cat", ""),
                         "ds": NEW_DATASET})
            print(f"\n已写入 {len(kept)} 道题（dataset={NEW_DATASET}）")

    if not (args.audit or args.seed or args.apply):
        print("用法：--audit 审计旧题 / --seed 验证新题 / --apply 全部执行并写库")


if __name__ == "__main__":
    asyncio.run(main())
