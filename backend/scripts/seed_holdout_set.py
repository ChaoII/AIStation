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
CASES: list[tuple[str, str, str, str]] = [
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


async def _check() -> None:
    _boot()
    print(f"[check] 共 {len(CASES)} 道题，逐条执行金标（看是否空结果/全空值）")
    bad = 0
    for i, (q, sql, _diff, _form) in enumerate(CASES, 1):
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
    print(f"[check] 有问题 {bad} 条 / {len(CASES)}")
    if bad:
        sys.exit(1)


async def _apply() -> None:
    _boot()
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.eval_set import list_cases, upsert_case

    for q, sql, diff, form in CASES:
        await upsert_case({
            "question": q, "gold_sql": sql, "datasource": DS,
            "difficulty": diff, "scenario": "留出集", "form": form,
            "tags": ["holdout", "frozen"], "verified": True, "enabled": True,
            "dataset": DATASET, "notes": "留出集：跑前冻结，不得据此调优",
        })
    n = len(await list_cases(datasource=DS, dataset=DATASET, enabled=True))

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
    exact = [q for q, *_ in CASES if any(str(f[0]) == q for f in few)]
    table_leak = []
    for q, sql, *_ in CASES:
        mine = _tables(sql)
        hit = [f[0] for f in few if mine & _tables(str(f[1] or ""))]
        if hit:
            table_leak.append((q, hit[:2]))
    h = hashlib.sha1("\n".join(sorted(q for q, *_ in CASES)).encode("utf-8")).hexdigest()[:16]
    print(f"[ok] {DATASET} 已落库 {n} 条；题目指纹 {h}")
    print(f"[ok] 泄漏检查：原题命中 {len(exact)} 条；示例 SQL 用到留出集表 {len(table_leak)} 条")
    for q, hit in table_leak[:5]:
        print(f"     - {q} :: {hit}")
    if exact or table_leak:
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验金标，不落库")
    ap.add_argument("--apply", action="store_true", help="落库（幂等）")
    args = ap.parse_args()
    if args.check:
        asyncio.run(_check())
    elif args.apply:
        asyncio.run(_apply())
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
