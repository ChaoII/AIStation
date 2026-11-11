"""全链路体检：105 题按难度/题型/场景拆分 + 时延/路径 + 本体/数据链路。

只读：不写评测表、不改数据。输出控制台报告并保存 JSON。

用法：
    cd backend
    uv run python scripts/health_report.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import Counter
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DS = "ds:6"
HIGH = {"困难", "较难", "hard"}
MID = {"中等", "medium"}
LOW = {"简单", "easy"}
RESULTS: list[dict] = []


def level(d: str) -> str:
    d = str(d or "")
    if d in HIGH:
        return "高"
    if d in MID:
        return "中"
    if d in LOW:
        return "低"
    return "题型标注"


def pct(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


def pctile(vals: list[int], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    return float(s[min(len(s) - 1, int(len(s) * q))])


async def run_eval(auth) -> None:
    from app.plugin.module_ai.query import eval_runner as R
    from app.plugin.module_ai.query.benchmark import load_label_synonyms
    from app.plugin.module_ai.query.eval_set import list_cases

    await load_label_synonyms()
    cases = (await list_cases(datasource="ds:4", enabled=True))[:105]
    for i, c in enumerate(cases, start=1):
        q = c["question"]
        t0 = time.perf_counter()
        try:
            d = await R._ask(q, auth, DS)
        except Exception as e:  # noqa: BLE001
            d = {"is_error": True, "answer": str(e)[:200], "rows": None, "path": "slow", "sql": ""}
        ms = int((time.perf_counter() - t0) * 1000)
        gc = await R._run_gold_sql(DS, c.get("gold_sql") or "")
        ok = R._lenient(d, {**c, "_gold_cols": gc.get("columns"), "_gold_rows": gc.get("rows")})
        RESULTS.append({
            "question": q, "ok": bool(ok), "difficulty": c.get("difficulty") or "",
            "form": c.get("form") or "", "scenario": c.get("scenario") or "",
            "path": d.get("path") or "", "is_error": bool(d.get("is_error")), "ms": ms,
            "metric": (d.get("metric") or {}).get("key", ""),
            "expected_metric": c.get("expected_metric") or "",
        })
        if i % 10 == 0:
            print(f"PROGRESS {i}/{len(cases)} ok={sum(1 for r in RESULTS if r['ok'])}", flush=True)


def summarize_eval() -> dict:
    n = len(RESULTS)
    ok = sum(1 for r in RESULTS if r["ok"])
    ms = [r["ms"] for r in RESULTS]
    paths = Counter(r["path"] for r in RESULTS)
    with_metric = [r for r in RESULTS if r["expected_metric"]]
    sem = sum(1 for r in with_metric if r["metric"] == r["expected_metric"])

    def by(field: str) -> list[tuple[str, int, int, float]]:
        out = []
        keys = sorted({r[field] for r in RESULTS})
        for k in keys:
            items = [r for r in RESULTS if r[field] == k]
            c = sum(1 for r in items if r["ok"])
            out.append((k, len(items), c, pct(c, len(items))))
        out.sort(key=lambda x: (-x[1], x[0]))
        return out

    levels = []
    for lv in ("低", "中", "高", "题型标注"):
        items = [r for r in RESULTS if level(r["difficulty"]) == lv]
        if items:
            c = sum(1 for r in items if r["ok"])
            levels.append((lv, len(items), c, pct(c, len(items))))

    return {
        "total": n, "ok": ok, "accuracy": pct(ok, n),
        "error_rate": pct(sum(1 for r in RESULTS if r["is_error"]), n),
        "fast_rate": pct(paths.get("fast", 0), n),
        "paths": dict(paths),
        "avg_ms": round(sum(ms) / n, 1) if n else 0,
        "p50_ms": pctile(ms, 0.5), "p95_ms": pctile(ms, 0.95),
        "semantic": pct(sem, len(with_metric)), "with_metric": len(with_metric),
        "by_difficulty": by("difficulty"), "by_level": levels,
        "by_form": by("form"), "by_scenario": by("scenario"),
        "fails": [r for r in RESULTS if not r["ok"]],
    }


async def ontology_stats() -> dict:
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.ontology import agent_tools as T
    from app.plugin.module_ai.ontology import service as ont

    async with async_db_session() as db:
        counts = {}
        for label, sql in (
            ("objects", "SELECT count(*) FROM ai_ont_object WHERE is_deleted=false"),
            ("properties", "SELECT count(*) FROM ai_ont_property WHERE is_deleted=false"),
            ("functions", "SELECT count(*) FROM ai_ont_function WHERE is_deleted=false"),
            ("actions", "SELECT count(*) FROM ai_ont_action WHERE is_deleted=false"),
            ("links", "SELECT count(*) FROM ai_ont_link WHERE is_deleted=false"),
            ("row_policies", "SELECT count(*) FROM ai_ont_row_policy WHERE is_deleted=false"),
            ("acl", "SELECT count(*) FROM ai_ont_resource_acl"),
            ("domains", "SELECT count(*) FROM ai_data_domain WHERE is_deleted=false"),
        ):
            try:
                counts[label] = int((await db.execute(text(sql))).scalar() or 0)
            except Exception:  # noqa: BLE001
                counts[label] = -1
    fuel_funcs = [f for f in await ont.list_functions(None)
                  if str(f.get("object_code", "")).startswith(("coal_", "fuel_"))]
    fuel_actions = [a for a in await ont.list_actions(None) if str(a.get("object_code", "")).startswith(("coal_", "fuel_"))]
    catalog = await T.ontology_catalog_text(20)
    schemas, names = await T.build_selected_ontology_tools(
        ["coal_settle_amount", "coal_ash_dry_basis", "coal_batch_annotate"], user_id=1)
    call = await T.run_selected_ontology_tool(
        "ont_fn__coal_settle_amount", {"qty": 1200, "price": 520}, user_id=1)
    return {
        "counts": counts,
        "fuel_functions": len(fuel_funcs), "fuel_actions": len(fuel_actions),
        "catalog_len": len(catalog), "catalog_has_fuel": "结算金额" in catalog,
        "tools": sorted(names), "tools_n": len(schemas),
        "function_call": call.get("result") if isinstance(call, dict) else str(call)[:80],
    }


async def data_stats() -> dict:
    from sqlalchemy import text

    from app.plugin.module_ai.query import executor as ex
    from app.plugin.module_ai.query import service as svc

    ds = await svc._load_ds(6)
    engine = ex.build_engine(svc._ds_cfg_from_model(ds))
    async with engine.connect() as conn:
        t = (await conn.execute(text(
            "SELECT count(*) FILTER (WHERE table_type='BASE TABLE'), count(*) FILTER (WHERE table_type='VIEW') "
            "FROM information_schema.tables WHERE table_schema='public'"))).fetchone()
        chain = (await conn.execute(text(
            'SELECT (SELECT count(*) FROM "FUEL_CB_COALCONTRACT"), '
            '(SELECT count(*) FROM "FUEL_CMCS_INFACTORYBATCH" WHERE "ID" LIKE \'DEMO-B-%\'), '
            '(SELECT count(*) FROM "FUEL_CMCS_RCSAMPLING" WHERE "ID" LIKE \'DEMO-SP-%\'), '
            '(SELECT count(*) FROM "FUEL_CMCS_MAKE" WHERE "ID" LIKE \'DEMO-MK-%\'), '
            '(SELECT count(*) FROM "FUEL_CMCS_ASSAY" WHERE "ID" LIKE \'DEMO-AS-%\'), '
            '(SELECT count(*) FROM "FUEL_CMCS_ELEMENTASSAY"), '
            '(SELECT count(*) FROM "FUEL_CB_COALBALANCE"), '
            '(SELECT count(*) FROM "CMMS_CANVAS")'))).fetchone()
    return {"base_tables": t[0], "views": t[1],
            "contracts": chain[0], "batches": chain[1], "sampling": chain[2],
            "makes": chain[3], "assays": chain[4], "details": chain[5],
            "settlements": chain[6], "canvases": chain[7]}


async def main() -> None:
    from main import create_app

    create_app()
    auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True, roles=[]))
    t0 = time.perf_counter()
    await run_eval(auth)
    summary = summarize_eval()
    onto = await ontology_stats()
    data = await data_stats()
    report = {"run_at": time.strftime("%Y-%m-%d %H:%M:%S"), "datasource": DS,
              "summary": summary, "ontology": onto, "data": data,
              "elapsed_s": round(time.perf_counter() - t0, 1)}
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "health_report_ds6.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print("\n=== SUMMARY ===")
    print(json.dumps({"total": summary["total"], "ok": summary["ok"],
                      "accuracy": summary["accuracy"], "fast_rate": summary["fast_rate"],
                      "avg_ms": summary["avg_ms"], "p50_ms": summary["p50_ms"],
                      "p95_ms": summary["p95_ms"], "semantic": summary["semantic"],
                      "error_rate": summary["error_rate"]}, ensure_ascii=False))
    print("LEVEL", summary["by_level"])
    print("DIFF", summary["by_difficulty"])
    print("FORM", summary["by_form"])
    print("SCENARIO", summary["by_scenario"][:10])
    print("FAIL", [(r["question"], r["path"]) for r in summary["fails"]])
    print("ONTOLOGY", json.dumps(onto, ensure_ascii=False, default=str))
    print("DATA", json.dumps(data, ensure_ascii=False, default=str))
    print("SAVED", out)


if __name__ == "__main__":
    asyncio.run(main())
