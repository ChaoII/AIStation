"""收敛 ds:4 的表范围到**关键业务表**（排除系统/技术表），并输出缺数据清单。

依据（`ds4_table_scope_report.py` 实测）：
- 业务表 192（燃煤/煤场/计量/化验/燃料…），其中 **99 张有数据**；
- 技术/系统表 92（SYS_*/EFMigrationsHistory/_BAK/_LOG…），其中 46 张有数据
  —— 这些正是"混进检索"的元凶；
- 其它 27。

做法：
1. ``ai_query_assets.included``：业务表 = true，技术/其它 = false（供检索/prompt 过滤）；
2. 非业务表的本体对象 ``enabled=false``（不让它们进本体语义上下文）；
3. 打印**缺数据清单**（业务表里 0 行的），供人工补数。

用法（backend 下）::

    python scripts/curate_ds4_scope.py --dry-run
    python scripts/curate_ds4_scope.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DS_ID = 4
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds4_table_scope_report import classify  # noqa: E402


async def main(dry: bool) -> None:
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query import executor as _ex
    from app.plugin.module_ai.query.service import _ds_cfg_from_model, _load_ds

    ds = await _load_ds(DS_ID)
    cfg = _ds_cfg_from_model(ds)
    res = await _ex.execute_select(
        cfg,
        "SELECT c.relname, (xpath('/row/c/text()', query_to_xml("
        "  'SELECT count(*) AS c FROM ' || quote_ident(c.relname), false, true, ''"
        ")))[1]::text::int AS cnt "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE c.relkind='r' AND n.nspname='public'",
    )
    counts = {str(r[0]).upper(): int(r[1] or 0) for r in res["rows"]}
    kind = {t: classify(t) for t in counts}

    on = sorted(t for t, k in kind.items() if k == "business")
    off = sorted(t for t, k in kind.items() if k != "business")
    print(f"ds:4 表 {len(counts)} 张：纳入 {len(on)}（业务），移出 {len(off)}（技术/其它）")

    async with async_db_session() as db:
        cur = {
            str(r[0]).upper(): bool(r[1])
            for r in (
                await db.execute(
                    text("SELECT table_name, included FROM ai_query_assets WHERE is_deleted=false")
                )
            ).fetchall()
        }
    to_on = [t for t in on if not cur.get(t, False)]
    to_off = [t for t in off if cur.get(t, False)]
    print(f"  需要置 included=true: {len(to_on)} 张；置 false: {len(to_off)} 张")

    # 缺数据清单（业务表里 0 行）
    empty_biz = [t for t in on if counts[t] == 0]
    print(f"\n=== 缺数据清单：业务表里 0 行的 {len(empty_biz)} 张（供补数）===")
    for t in empty_biz[:60]:
        print(f"  {t}")
    if len(empty_biz) > 60:
        print(f"  ...（其余 {len(empty_biz) - 60} 张见脚本输出/CSV）")

    print(f"\n=== 移出范围的技术/系统表（{len(off)} 张，前 30）===")
    for t in off[:30]:
        print(f"  {t}  (rows={counts[t]})")

    if dry:
        print("\n[dry-run] 未写入")
        return

    async with async_db_session.begin() as db:
        if to_on:
            await db.execute(
                text(
                    "UPDATE ai_query_assets SET included=true, updated_time=now() "
                    "WHERE is_deleted=false AND table_name = ANY(:t)"
                ),
                {"t": to_on},
            )
        if to_off:
            await db.execute(
                text(
                    "UPDATE ai_query_assets SET included=false, updated_time=now() "
                    "WHERE is_deleted=false AND table_name = ANY(:t)"
                ),
                {"t": to_off},
            )
        # 非业务表的本体对象禁用（不进本体语义上下文）
        await db.execute(
            text(
                "UPDATE ai_ont_object SET enabled=false, updated_time=now() "
                "WHERE is_deleted=false AND datasource_id=:d AND UPPER(COALESCE(backing_table,'')) = ANY(:t)"
            ),
            {"d": DS_ID, "t": off},
        )
    print(f"\n完成：纳入 {len(on)} 张业务表，移出 {len(off)} 张技术/系统表，"
          f"并禁用对应本体对象")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.dry_run))
