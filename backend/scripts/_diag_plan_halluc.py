"""取证：两段式分解为什么会出现表名幻觉。

第 1 步（不花模型钱）：从那次 A/B 实验的逐题结果里，找出**生成了不存在表名**的题，
对比它的金标表名 —— 说明幻觉在哪个阶段出现。
第 2 步：只调用**计划阶段**（一次 LLM），看它自己返回的 plan 里写了什么表。
"""

from __future__ import annotations

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

#: 日志里出现过的"明显不像本库风格"的名字（真实表全是大写下划线：FUEL_*/CMMS_*/DTXY_*）
SUSPECT = ("bunker", "bunker_entry", "facility", "measure_point", "camera", "user", "orders")


async def main() -> None:
    from main import create_app

    create_app()
    # 找最近两轮 run（A/B）
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.eval_set import load_results
    from app.plugin.module_ai.query.service import AiQueryService

    async with async_db_session() as db:
        runs = (
            await db.execute(
                text(
                    "SELECT run_id, started_at, status FROM ai_query_testrun "
                    "WHERE is_deleted=false ORDER BY id DESC LIMIT 4"
                )
            )
        ).fetchall()
    print("最近的 run：")
    for r in runs:
        print(f"  {r[0]}  {r[1]}  {r[2]}")

    # 逐个 run 找幻觉题
    for rid, _t, _s in runs:
        rows = await load_results(rid)
        bad = []
        for r in rows:
            sql = str(r.get("model_sql") or r.get("sql") or "")
            low = sql.lower()
            hits = [s for s in SUSPECT if re.search(rf"\b{re.escape(s)}\b", low)]
            if hits:
                bad.append((r, hits))
        if bad:
            print(f"\n=== run {rid} 里疑似幻觉 {len(bad)} 题 ===")
            for r, hits in bad[:6]:
                print(f"  问：{r['question'][:44]}")
                print(f"    幻觉名：{hits}")
                print(f"    生成：{(r.get('model_sql') or r.get('sql') or '')[:150]}")
                gt = r.get("gold_tables") or []
                print(f"    金标表：{gt}")
                print(f"    金标：{(r.get('gold_sql') or '')[:150]}")

    # —— 第 2 步：单独看"计划阶段"说了什么 ——
    q = "每个原煤仓的累计入仓煤量前 3 名"
    print(f"\n=== 只调用计划阶段：{q} ===")
    runtime = await AiQueryService._get_runtime()
    from app.plugin.module_ai.query.plan import format_plan, parse_plan, plan_prompt

    raw = await AiQueryService._plan_llm(plan_prompt(q), runtime, 0.0)
    print("计划原文：\n" + str(raw)[:900])
    plan = parse_plan(raw)
    print(f"\n解析出的 tables = {(plan or {}).get('tables')}")
    print(f"注入到第二段 prompt 的内容：\n{format_plan(plan) if plan else '(降级，未注入)'}")


asyncio.run(main())
