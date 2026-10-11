"""ds:4 表范围盘点：业务 vs 技术、有没有数据、是否已纳入资产目录。

用途：为"选关键业务表（~100+，排除系统表）"提供可复核依据。

用法（backend 下）::

    python scripts/ds4_table_scope_report.py            # 控制台摘要
    python scripts/ds4_table_scope_report.py --csv out.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
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

DS_ID = 4

#: 业务域前缀（燃煤/煤场/计量/化验/燃料等）
BIZ_PREFIXES = ("FUEL_", "CMMS_", "DTXY_", "FR_", "RPT_", "EQUIPMENT", "GEN_")

#: 明确的技术/系统表（不属于业务问数范围）
TECH_RE = re.compile(
    r"^(SYS_|EFMigrationsHistory|__)|(_BAK|_HIS|_HISTORY|_LOG|_LOGS|_TEMP|_TMP)$",
    re.IGNORECASE,
)


def classify(name: str) -> str:
    n = str(name).upper()
    if TECH_RE.search(n):
        return "technical"
    if n.startswith(BIZ_PREFIXES):
        return "business"
    return "other"


async def main(csv_path: str | None) -> None:
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query import executor as _ex
    from app.plugin.module_ai.query.service import _ds_cfg_from_model, _load_ds

    ds = await _load_ds(DS_ID)
    cfg = _ds_cfg_from_model(ds)

    # 一次查询拿到所有表的行数（query_to_xml 技巧，避免 331 次往返）
    res = await _ex.execute_select(
        cfg,
        "SELECT c.relname, "
        "(xpath('/row/c/text()', query_to_xml("
        "  'SELECT count(*) AS c FROM ' || quote_ident(c.relname), false, true, ''"
        ")))[1]::text::int AS cnt "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE c.relkind='r' AND n.nspname='public'",
    )
    counts = {str(r[0]).upper(): int(r[1] or 0) for r in res["rows"]}

    async with async_db_session() as db:
        assets = {
            str(r[0]).upper(): (bool(r[1]), str(r[2] or ""), str(r[3] or ""))
            for r in (
                await db.execute(
                    text(
                        "SELECT table_name, included, COALESCE(alias,''), COALESCE(domain,'') "
                        "FROM ai_query_assets WHERE is_deleted=false"
                    )
                )
            ).fetchall()
        }
        objs = {
            str(r[0]).upper()
            for r in (
                await db.execute(
                    text(
                        "SELECT COALESCE(backing_table,'') FROM ai_ont_object "
                        "WHERE is_deleted=false AND datasource_id=:d"
                    ),
                    {"d": DS_ID},
                )
            ).fetchall()
        }
        schema = {
            str(r[0]).upper(): str(r[1] or "")
            for r in (
                await db.execute(
                    text(
                        "SELECT table_name, COALESCE(table_comment,'') FROM ai_query_schema "
                        "WHERE is_deleted=false AND datasource=:c"
                    ),
                    {"c": f"ds:{DS_ID}"},
                )
            ).fetchall()
        }

    rows = []
    for t in sorted(counts):
        kind = classify(t)
        inc, alias, domain = assets.get(t, (False, "", ""))
        rows.append({
            "table": t, "kind": kind, "rows": counts[t],
            "included": inc, "has_object": t in objs,
            "comment": schema.get(t, ""), "alias": alias, "domain": domain,
        })

    stat: dict[str, dict] = {}
    for r in rows:
        s = stat.setdefault(r["kind"], {"n": 0, "nonempty": 0, "included": 0, "obj": 0})
        s["n"] += 1
        s["nonempty"] += 1 if r["rows"] > 0 else 0
        s["included"] += 1 if r["included"] else 0
        s["obj"] += 1 if r["has_object"] else 0

    print(f"ds:4 共 {len(rows)} 张表")
    for k, s in sorted(stat.items()):
        print(f"  {k:10s} 表={s['n']:4d} 有数据={s['nonempty']:4d} "
              f"已纳入资产={s['included']:4d} 有本体对象={s['obj']:4d}")

    print("\n=== 业务表里有数据的（这些才是评测/指标的可用基础）===")
    biz_nonempty = [r for r in rows if r["kind"] == "business" and r["rows"] > 0]
    biz_nonempty.sort(key=lambda r: -r["rows"])
    for r in biz_nonempty[:40]:
        print(f"  {r['table']:42s} rows={r['rows']:>7d} incl={int(r['included'])} "
              f"obj={int(r['has_object'])} {r['comment'][:24]}")

    print(f"\n业务表总数={sum(1 for r in rows if r['kind'] == 'business')}，"
          f"其中有数据={len(biz_nonempty)}")
    print(f"技术/系统表={sum(1 for r in rows if r['kind'] == 'technical')}，"
          f"其它={sum(1 for r in rows if r['kind'] == 'other')}")

    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\n已导出 {csv_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()
    asyncio.run(main(a.csv))
