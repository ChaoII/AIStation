"""反馈闭环：把**评测判错的题**沉淀成 few-shot（模型从错题里学）。

原则（避免自欺）：
1. 只沉淀**判错/报错**的题（答对的不需要教）；
2. 金标必须**执行通过且非退化**（否则教的是错的）；
3. 与已有示例去重；带 ``auto-curated`` 标记，可一键回滚；
4. 沉淀后要用同一套评测**复测证明真的涨了**，否则应回滚。
"""
from __future__ import annotations


def select_fewshot_candidates(results: list[dict], gold_by_question: dict[str, str],
                              skip_questions: set[str] | None = None) -> list[dict]:
    """从评测结果里挑「值得沉淀成 few-shot」的错题。

    过滤：判错且非退化、金标可用、未沉淀过（``skip_questions``）。
    """
    skip = skip_questions or set()
    out: list[dict] = []
    for r in results or []:
        if r.get("degenerate") or r.get("gold_match"):
            continue
        q = str(r.get("question") or "").strip()
        sql = str((gold_by_question or {}).get(q) or "").strip()
        if not q or not sql or q in skip:
            continue
        out.append({"question": q, "gold_sql": sql})
    return out


# ---------------------------------------------------------------------------
# IO 钩子（可注入，便于纯逻辑测试）
# ---------------------------------------------------------------------------
async def _load_results(run_id: str) -> list[dict]:
    from .eval_set import load_results

    return await load_results(run_id)


async def _list_cases(**kwargs) -> list[dict]:
    from .eval_set import list_cases

    return await list_cases(**kwargs)


async def _list_fewshots(datasource: str | None = None) -> list[dict]:
    from .service import AiQueryService

    return await AiQueryService.list_fewshots(datasource)


async def _run_gold(sql: str, datasource: str, auth=None) -> dict:
    from .eval_generate import _run_gold as _g

    return await _g(sql, datasource, auth)


async def _add_fewshot(data: dict, auth=None) -> dict:
    import uuid

    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        await db.execute(
            text(
                "INSERT INTO ai_query_fewshot(datasource,question,sql,enabled,description,"
                "status,uuid,is_deleted,created_time,updated_time) "
                "VALUES(:d,:q,:s,true,:desc,'0',:u,false,now(),now())"
            ),
            {"d": data.get("datasource") or "system", "q": data["question"],
             "s": data["gold_sql"], "desc": data.get("description") or "",
             "u": uuid.uuid4().hex},
        )
    return {"ok": True}


async def curate_from_run(run_id: str, datasource: str, auth=None) -> dict:
    """把某轮评测里**判错的题**沉淀成 few-shot（金标经执行验证、非退化才入库）。"""
    from .eval_metrics import is_degenerate_result

    results = await _load_results(run_id)
    cases = await _list_cases(datasource=datasource)
    gold = {str(c.get("question") or ""): str(c.get("gold_sql") or "") for c in cases}
    existing = await _list_fewshots(datasource)
    skip = {str(f.get("question") or "") for f in existing}

    cands = select_fewshot_candidates(results, gold, skip)
    added = skipped = 0
    for c in cands:
        res = await _run_gold(c["gold_sql"], datasource, auth)
        if not res.get("ok") or not res.get("rows") or is_degenerate_result(res["rows"]):
            skipped += 1
            continue
        await _add_fewshot(
            {"question": c["question"], "gold_sql": c["gold_sql"], "datasource": datasource,
             "description": "auto-curated:from-run"},
            auth,
        )
        added += 1
    return {"run_id": run_id, "candidates": len(cands), "added": added, "skipped": skipped}
