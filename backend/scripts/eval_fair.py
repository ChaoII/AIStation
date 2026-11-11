"""公平口径评测：**保留指标/本体/术语**，但剔除与考题原题/近似的 few-shot。

用法：uv run python scripts/eval_fair.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DS = "ds:6"


def norm(s: str) -> str:
    return re.sub(r"[\s\"'`]+", "", (s or "").lower())


async def main() -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query import eval_runner as R
    from app.plugin.module_ai.query import metric_rules as M
    from app.plugin.module_ai.query.benchmark import load_label_synonyms
    from app.plugin.module_ai.query.eval_set import list_cases
    from app.plugin.module_ai.query.service import AiQueryService as S
    from main import create_app

    create_app()
    await load_label_synonyms()
    cases = (await list_cases(datasource=DS, enabled=True))[:105]
    questions = [c["question"] for c in cases]
    async with async_db_session() as db:
        few = (await db.execute(text(
            "SELECT question,sql FROM ai_query_fewshot WHERE datasource=:d AND is_deleted=false AND enabled=true"
        ), {"d": DS})).fetchall()

    # 只保留“与任何考题都不相同、也不高度相似”的示例
    general = []
    for q, s in few:
        if any(norm(q) == norm(t) or M.score_fewshot(t, q) >= 3 for t in questions):
            continue
        general.append({"q": q, "sql": s})
    print(f"[fewshot] total={len(few)} kept_general={len(general)} removed={len(few) - len(general)}")

    async def _general(cls, *a, **k):
        return general
    S._dynamic_fewshots = classmethod(_general)

    auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
    ok = 0
    fails = []
    for i, c in enumerate(cases, start=1):
        q = c["question"]
        try:
            d = await R._ask(q, auth, DS)
        except Exception as e:  # noqa: BLE001
            d = {"is_error": True, "rows": None, "path": "slow", "answer": str(e)[:120]}
        gc = await R._run_gold_sql(DS, c.get("gold_sql") or "")
        m = R._lenient(d, {**c, "_gold_cols": gc.get("columns"), "_gold_rows": gc.get("rows")})
        ok += 1 if m else 0
        if not m:
            fails.append((q, d.get("is_error"), str(d.get("rows"))[:40], str(gc.get("rows"))[:40]))
        if i % 10 == 0:
            print(f"PROGRESS {i}/{len(cases)} ok={ok}", flush=True)
    print("FAIR_RESULT", ok, "/", len(cases), "=", round(ok / len(cases), 4))
    for f in fails:
        print("FAIR_FAIL", f)


if __name__ == "__main__":
    asyncio.run(main())
