"""问数召回评测：Recall@k（从金标 SQL 抽「应使用的表」作为 ground truth）。

用法（在 backend 下运行，需 dev 数据库）：
    uv run python -m app.plugin.module_ai.query.recall_eval --k=8
    uv run python -m app.plugin.module_ai.query.recall_eval --k=8 --compare   # 新旧召回对比
    uv run python -m app.plugin.module_ai.query.recall_eval --k=8 --no-rebuild

说明：
- **不调 LLM**，只测「召回」，因此很快（秒级~分钟级）。
- ground truth = 金标 SQL 里 ``FROM/JOIN`` 出现的表 ∩ 当前 schema。
- ``--compare`` 同时跑旧实现 ``_semantic_tables_legacy``，直接给出前后对比。
"""
from __future__ import annotations

import asyncio
import os
import re
import sys

os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

_TABLE_RE = re.compile(r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def _gold_tables(sql: str, schema: dict) -> set[str]:
    return {t for t in _TABLE_RE.findall(sql or "") if t in schema}


async def _run(k: int, compare: bool, rebuild: bool) -> None:
    from main import create_app

    create_app()  # 触发模块发现，加载全部 ORM 模型

    from app.plugin.module_ai.query.benchmark import NL2SQL_GOLDEN
    from app.plugin.module_ai.query.service import AiQueryService as S

    if rebuild:
        info = await S.rebuild_recall_units()
        print(f"[召回单元] {info['units']} 条（向量化 {info['embedded']}）")

    schema = await S._system_schema()
    print(f"schema 表数 = {len(schema)}；题目数 = {len(NL2SQL_GOLDEN)}；k = {k}\n")

    def _score(rows: list[tuple[str, set[str], list[str]]]) -> float:
        if not rows:
            return 0.0
        return sum(len(gt & set(rec[:k])) / len(gt) for _, gt, rec in rows if gt) / max(
            1, sum(1 for _, gt, _ in rows if gt)
        )

    new_rows: list[tuple[str, set[str], list[str]]] = []
    old_rows: list[tuple[str, set[str], list[str]]] = []
    for item in NL2SQL_GOLDEN:
        q, gold = item["q"], item.get("gold") or ""
        gt = _gold_tables(gold, schema)
        if not gt:
            continue
        rec_new = await S._semantic_tables_uncached(q, schema, None, None)
        new_rows.append((q, gt, rec_new))
        if compare:
            rec_old = await S._semantic_tables_legacy(q, schema, None, None)
            old_rows.append((q, gt, rec_old))

    def _report(name: str, rows: list[tuple[str, set[str], list[str]]]) -> None:
        full_miss = [q for q, gt, rec in rows if not (gt & set(rec[:k]))]
        print(f"=== {name} ===")
        print(f"Recall@{k} = {_score(rows):.1%}   完全未命中 {len(full_miss)}/{len(rows)} 题")
        for q in full_miss[:10]:
            print(f"   ✗ {q}")
        print()

    if compare:
        _report("旧实现（分级短路 + 字典序截断）", old_rows)
    _report("新实现（并行四路 + RRF + 按分数 top_k）", new_rows)


def main() -> None:
    k, compare, rebuild = 8, False, True
    for a in sys.argv[1:]:
        if a.startswith("--k="):
            k = int(a.split("=", 1)[1])
        elif a == "--compare":
            compare = True
        elif a == "--no-rebuild":
            rebuild = False
    asyncio.run(_run(k, compare, rebuild))


if __name__ == "__main__":
    main()
