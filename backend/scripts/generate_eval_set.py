"""生成问数评测测试集（LLM 出题 + 金标执行校验），补足到目标题数。

用法（在 ``backend`` 下）::

    python scripts/generate_eval_set.py --ds=system --target=55
    python scripts/generate_eval_set.py --ds=ds:4  --target=45
    python scripts/generate_eval_set.py --ds=both  --target=100

要点：**每题的金标 SQL 都会在对应数据源上真实执行**，失败/空结果不入集（见 ``eval_generate``）。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

#: 出题矩阵（难度 × 形式）——覆盖 spec 要求的多难度/多形式。
MATRIX: tuple[tuple[str, str], ...] = (
    ("简单", "单维统计"), ("简单", "快路径指标"), ("简单", "排名TopN"),
    ("中等", "多维报表"), ("中等", "联表"), ("中等", "占比"),
    ("中等", "业务黑话"), ("困难", "时间窗口"), ("困难", "窗口函数"),
    ("困难", "嵌套子查询"), ("困难", "去重"),
)


def _auth():
    return SimpleNamespace(user=SimpleNamespace(id=1))


async def _schema_rows(datasource: str) -> list[dict]:
    from app.plugin.module_ai.query.service import SYSTEM_DS, AiQueryService, list_ds_schema

    if datasource == SYSTEM_DS:
        schema = await AiQueryService._system_schema()
        return [
            {"table": t, "comment": "", "columns": [
                {"name": c.split("(", 1)[0], "comment": ""} for c in cols]}
            for t, cols in schema.items()
        ]
    # ⚠️ 自定义数据源只给**已纳入范围**的表（业务且有数据）——
    # 旧实现给全部同步表，出题模型会拿空表出题 → 金标必空/退化。
    return await list_ds_schema(int(datasource.split(":")[-1]), included_only=True)


async def _relations(datasource: str) -> list[str]:
    """可用的表间关联（联表出题用）。取本体关系边里有字段映射的。"""
    try:
        from app.plugin.module_ai.ontology import semantic as _sem

        ctx = await _sem.semantic_context(include_properties=False)
        out: list[str] = []
        for r in ctx.get("relations") or []:
            sf, tf = r.get("source_field"), r.get("target_field")
            if sf and tf:
                out.append(f"{r.get('source')}.{sf} → {r.get('target')}.{tf}")
        return out
    except Exception as e:  # noqa: BLE001
        print(f"  （读取关联失败，联表题将无关联提示: {str(e)[:60]}）")
        return []


async def generate_for(datasource: str, target: int, per_round: int, auth,
                       generation_only: bool = False,
                       forms: list[str] | None = None) -> dict:
    from app.plugin.module_ai.query.eval_generate import (
        build_prompt, call_llm, parse_cases, verify_and_save,
    )
    from app.plugin.module_ai.query.eval_set import list_cases
    from app.plugin.module_ai.query.service import SYSTEM_DS, AiQueryService

    ds_code = SYSTEM_DS if datasource in ("system", SYSTEM_DS) else datasource
    schema = await _schema_rows(ds_code)
    metrics = await AiQueryService.list_metrics(ds_code)
    terms = await AiQueryService.list_terms(ds_code)
    rels = await _relations(ds_code)
    matrix = tuple((d, f) for d, f in MATRIX if not forms or f in forms) or MATRIX
    have = len(await list_cases(datasource=ds_code))
    print(f"[{ds_code}] 已有 {have} 题，目标 {target}；表 {len(schema)} 张，"
          f"指标 {len(metrics)}，术语 {len(terms)}，关联 {len(rels)}；"
          f"generation_only={generation_only}")

    round_i = 0
    saved_total = rejected_total = metric_rejected = 0
    while have < target and round_i < 60:
        difficulty, form = matrix[round_i % len(matrix)]
        round_i += 1
        need = min(per_round, target - have)
        text = await call_llm(
            build_prompt(schema, metrics, terms, difficulty, form, need, relations=rels)
        )
        cases = parse_cases(text)
        if not cases:
            print(f"  轮 {round_i}（{difficulty}/{form}）LLM 未产出可解析用例，跳过")
            continue
        # ⚠️ 维度以**调用方请求**为准：实测模型会忽略提示里指定的难度/形式（一律回「简单」）
        for c in cases:
            c["difficulty"] = difficulty
            c["form"] = form
        out = await verify_and_save(cases, ds_code, auth, generation_only=generation_only)
        saved_total += out["saved"]
        rejected_total += out["rejected"]
        metric_rejected += out.get("rejected_metric", 0)
        have = len(await list_cases(datasource=ds_code))
        print(f"  轮 {round_i}（{difficulty}/{form}）：收 {out['saved']} / 拒 {out['rejected']}"
              f" / 指标可答拒 {out.get('rejected_metric', 0)} → 累计 {have}")
    return {"datasource": ds_code, "have": have, "saved": saved_total,
            "rejected": rejected_total, "rejected_metric": metric_rejected}


async def main(ds: str, target: int, per_round: int, generation_only: bool = False,
               forms: list[str] | None = None) -> None:
    from main import create_app

    create_app()
    from app.plugin.module_ai.query.eval_set import ensure_eval_tables, list_cases

    await ensure_eval_tables()
    auth = _auth()
    targets = (
        [("system", target // 2), ("ds:4", target - target // 2)]
        if ds == "both"
        else [(("system" if ds == "system" else ds), target)]
    )
    for code, t in targets:
        await generate_for(code, t, per_round, auth, generation_only, forms)

    print("\n=== 测试集分布 ===")
    rows = await list_cases()
    from collections import Counter

    for f in ("datasource", "difficulty", "form", "scenario"):
        c = Counter(str(r.get(f) or "未分类") for r in rows)
        print(f"  {f}: " + ", ".join(f"{k}={v}" for k, v in c.most_common()))
    print(f"  合计 {len(rows)} 题，其中 verified={sum(1 for r in rows if r['verified'])}，"
          f"退化={sum(1 for r in rows if r.get('degenerate'))}，"
          f"指标可答={sum(1 for r in rows if r.get('metric_eligible'))}")


def cli() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", default="both", help="system | ds:4 | both")
    ap.add_argument("--target", type=int, default=100)
    ap.add_argument("--per-round", type=int, default=8)
    ap.add_argument("--generation-only", action="store_true",
                    help="只收**指标快路径答不了**的题（考模型生成能力）")
    ap.add_argument("--forms", default="", help="逗号分隔，只出这些形式（如 联表,占比,时间窗口）")
    a = ap.parse_args()
    forms = [f.strip() for f in a.forms.split(",") if f.strip()]
    asyncio.run(main(a.ds, a.target, a.per_round, a.generation_only, forms))


if __name__ == "__main__":
    cli()
