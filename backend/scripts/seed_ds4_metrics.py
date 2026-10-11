"""为 ds:4 批量播种**可执行**指标（只建在**有数据**的业务表上，逐条执行验证）。

背景：ds:4 原来只有 4 个指标（且 3 个建在 0 行表上 → 恒返回 NULL），
对 184 张业务表来说远远不够。

做法：
1. 取业务表里有数据的（行数 > 0）；
2. 每张建一个「条数」指标（``COUNT(*)``）；
3. 数值型且业务味明显的列（QTY/WEIGHT/AMOUNT/PRICE/MONEY/TON/RZ…）建「合计/平均」指标；
4. **每条都先在目标库执行**，跑通且结果非 NULL 才入库。

用法（backend 下）::

    python scripts/seed_ds4_metrics.py --dry-run
    python scripts/seed_ds4_metrics.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DS_ID = 4
DS = f"ds:{DS_ID}"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds4_table_scope_report import classify  # noqa: E402

#: 数值列里"业务味"明显的（用于生成合计/平均指标）
NUMERIC_HINT = re.compile(
    r"(QTY|QUANTITY|AMOUNT|WEIGHT|PRICE|MONEY|COST|TON|RZ|LF|QSF|HFF|HF|HRD|KMXS|"
    r"RATE|RATIO|PERCENT|TOTAL|SUM|AVG|NUM|COUNT|VALUE)",
    re.IGNORECASE,
)
NUMERIC_TYPES = {"numeric", "integer", "bigint", "smallint", "real", "double precision",
                 "decimal", "money"}
#: 生成「条数」指标的业务表上限（按行数倒序取前 N，避免指标爆炸）
MAX_COUNT_METRICS = 40
MAX_SUM_METRICS = 30


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(name).lower()).strip("_")[:60]


async def main(dry: bool) -> None:
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query import executor as _ex
    from app.plugin.module_ai.query.service import _ds_cfg_from_model, _load_ds

    ds = await _load_ds(DS_ID)
    cfg = _ds_cfg_from_model(ds)

    counts_res = await _ex.execute_select(
        cfg,
        "SELECT c.relname, (xpath('/row/c/text()', query_to_xml("
        "  'SELECT count(*) AS c FROM ' || quote_ident(c.relname), false, true, ''"
        ")))[1]::text::int AS cnt "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE c.relkind='r' AND n.nspname='public'",
    )
    counts = {str(r[0]).upper(): int(r[1] or 0) for r in counts_res["rows"]}
    biz = sorted(
        (t for t, c in counts.items() if classify(t) == "business" and c > 0),
        key=lambda t: -counts[t],
    )
    print(f"有数据的业务表 {len(biz)} 张")

    # 表注释（做中文名）
    comments: dict[str, str] = {}
    async with async_db_session() as db:
        for r in (
            await db.execute(
                text(
                    "SELECT table_name, COALESCE(table_comment,'') FROM ai_query_schema "
                    "WHERE is_deleted=false AND datasource=:c"
                ),
                {"c": DS},
            )
        ).fetchall():
            comments[str(r[0]).upper()] = str(r[1] or "")
        have = {
            str(r[0])
            for r in (
                await db.execute(
                    text(
                        "SELECT key FROM ai_query_metrics WHERE is_deleted=false AND datasource=:d"
                    ),
                    {"d": DS},
                )
            ).fetchall()
        }
    print(f"现有指标 {len(have)} 个")

    # 数值列（按表）
    col_res = await _ex.execute_select(
        cfg,
        "SELECT table_name, column_name, data_type, COALESCE(col_description("
        "  (SELECT oid FROM pg_class WHERE relname=table_name LIMIT 1), ordinal_position), '') "
        "FROM information_schema.columns WHERE table_schema='public'",
    )
    num_cols: dict[str, list[tuple[str, str]]] = {}
    for t, c, dt, _desc in col_res["rows"]:
        T, C, DT = str(t).upper(), str(c).upper(), str(dt).lower()
        if T in biz and DT in NUMERIC_TYPES and NUMERIC_HINT.search(C):
            num_cols.setdefault(T, []).append((C, DT))

    plan: list[dict] = []
    for t in biz[:MAX_COUNT_METRICS]:
        cn = comments.get(t) or t
        plan.append({
            "key": f"count_{_key(t)}", "name": f"{cn}条数",
            "description": f"{cn}（{t}）的记录条数",
            "sql_template": f'SELECT COUNT(*) AS "数值" FROM "{t}"',
            "agg": "count", "unit": "条",
        })
    used_sum = 0
    for t in biz:
        if used_sum >= MAX_SUM_METRICS:
            break
        for c, _dt in num_cols.get(t, [])[:1]:
            cn = comments.get(t) or t
            plan.append({
                "key": f"sum_{_key(t)}_{_key(c)}", "name": f"{cn}{c}合计",
                "description": f"{cn}（{t}）的 {c} 合计",
                "sql_template": f'SELECT SUM("{c}") AS "数值" FROM "{t}"',
                "agg": "sum", "unit": "",
            })
            used_sum += 1
            if used_sum >= MAX_SUM_METRICS:
                break

    plan = [p for p in plan if p["key"] not in have]
    print(f"计划新增指标 {len(plan)} 个（条数 {sum(1 for p in plan if p['agg'] == 'count')}，"
          f"合计 {sum(1 for p in plan if p['agg'] == 'sum')}）")

    ok: list[dict] = []
    bad: list[str] = []
    for p in plan:
        try:
            r = await _ex.execute_select(cfg, p["sql_template"])
            rows = r["rows"] or []
            if not rows or all(v is None for row in rows for v in row):
                bad.append(f"{p['key']}: 结果为空/NULL")
                continue
            ok.append(p)
        except Exception as e:  # noqa: BLE001
            bad.append(f"{p['key']}: {str(e)[:80]}")
    print(f"验证通过 {len(ok)}，跳过 {len(bad)}")
    for b in bad[:6]:
        print("  - 跳过", b)

    if dry:
        for p in ok[:10]:
            print("  +", p["key"], "=>", p["sql_template"])
        print("\n[dry-run] 未写入")
        return

    async with async_db_session.begin() as db:
        for i, p in enumerate(ok):
            await db.execute(
                text(
                    "INSERT INTO ai_query_metrics(datasource,key,name,description,sql_template,"
                    "params,dimensions,agg,unit,permission_tag,enabled,sort,cache_ttl,uuid,status,"
                    "is_deleted,created_time,updated_time) "
                    "VALUES(:d,:k,:n,:desc,:sql,'[]','[]',:agg,:unit,'',true,:sort,0,:u,'0',false,"
                    "now(),now())"
                ),
                {"d": DS, "k": p["key"], "n": p["name"], "desc": p["description"],
                 "sql": p["sql_template"], "agg": p["agg"], "unit": p["unit"],
                 "sort": 100 + i, "u": uuid.uuid4().hex},
            )
    print(f"\n已写入 {len(ok)} 个 ds:4 指标")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.dry_run))
