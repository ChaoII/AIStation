"""把本体对象从 ds:4（远端）重新绑定到 ds:6（本地副本，当前默认数据源）。

背景（2026-11-12 实测）：`ai_ont_object.datasource_id` 仍指向 ds:4，而问数默认已切到 ds:6，
于是同一个业务对象两套数字 —— 入厂批次 287(ds4) vs 577(ds6)、燃煤合同 0 vs 120。

用法：
    uv run python scripts/rebind_ontology_ds.py --dry-run
    uv run python scripts/rebind_ontology_ds.py --apply
    uv run python scripts/rebind_ontology_ds.py --apply --from 4 --to 6

只处理 `datasource_id = --from` 的对象；表在目标数据源不存在时跳过（保底不动）。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


async def _target_tables(to_id: int) -> set[str]:
    from app.plugin.module_ai.query.service import list_ds_schema

    try:
        rows = await list_ds_schema(to_id)
        return {str(r["table"]).upper() for r in rows}
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 取 ds:{to_id} 表清单失败（将按全部可迁处理）: {e}")
        return set()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", type=int, default=4)
    ap.add_argument("--to", dest="dst", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        ap.print_help()
        return

    from main import create_app

    create_app()

    from sqlalchemy import text

    from app.core.database import async_db_session

    tables = await _target_tables(args.dst)
    async with async_db_session() as db:
        rows = (await db.execute(text(
            "SELECT code, name, COALESCE(backing_table,''), datasource_id FROM ai_ont_object "
            "WHERE is_deleted=false AND datasource_id=:s ORDER BY code"
        ), {"s": args.src})).fetchall()
    print(f"[plan] ds:{args.src} → ds:{args.dst}；候选对象 {len(rows)} 个；目标表 {len(tables)} 张")

    movable, skipped = [], []
    for code, name, backing, _dx in rows:
        tbl = (backing or code).upper()
        if tables and tbl not in tables:
            skipped.append((code, tbl))
            continue
        movable.append((code, name, tbl))

    print(f"[plan] 可迁 {len(movable)} 个、跳过 {len(skipped)} 个（目标库没有对应表）")
    for code, tbl in skipped[:10]:
        print("  SKIP", code, "→", tbl)

    if args.dry_run:
        for code, name, tbl in movable[:10]:
            print("  MOVE", code, "|", name, "|", tbl)
        return

    if not movable:
        print("[done] 没有可迁对象")
        return
    async with async_db_session.begin() as db:
        await db.execute(text(
            "UPDATE ai_ont_object SET datasource_id=:d, updated_time=now() "
            "WHERE is_deleted=false AND datasource_id=:s AND upper(coalesce(backing_table, code)) = ANY(:tbls)"
        ), {"d": args.dst, "s": args.src, "tbls": [t for _, _, t in movable]})
        left = (await db.execute(text(
            "SELECT count(*) FROM ai_ont_object WHERE is_deleted=false AND datasource_id=:s"
        ), {"s": args.src})).scalar()
    print(f"[ok] 已迁 {len(movable)} 个对象到 ds:{args.dst}；仍绑 ds:{args.src} 的剩 {left} 个")


if __name__ == "__main__":
    asyncio.run(main())
