"""为 ds:4 补齐本体关系的**归属标记** + 导入目标库真实外键。

排查纠正（重要）：ds:4 **并不是没有 join 边**——燃煤域已有 **189 条**带字段映射的关系边
（`FUEL_CMCS_GOODSTRANSPORT.GOODSTYPEID → FUEL_CMCS_GOODSTYPE.ID` 等）。
真正的问题是这些对象的 `datasource_id` 是 **NULL**（创建时没打标），
于是「按数据源过滤」的诊断/运营视图全都看不到它们。

本脚本做两件事（均先验证再写）：
1. **回填**：`backing_table` 命中目标库真实表名的对象 → `datasource_id=<DS_ID>`；
2. **补真实外键**：把目标库 `information_schema` 的外键（两端都有本体对象）写成关系边
   （`join_method='foreign_key'`）。

用法（backend 下）::

    python scripts/seed_ds4_joins.py --dry-run
    python scripts/seed_ds4_joins.py
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


async def main(dry: bool) -> None:
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.ontology.service import upsert_link
    from app.plugin.module_ai.query import executor as _ex
    from app.plugin.module_ai.query.service import _ds_cfg_from_model, _load_ds

    # 目标库真实表（权威来源）
    ds = await _load_ds(DS_ID)
    cfg = _ds_cfg_from_model(ds)
    cols = await _ex.execute_select(
        cfg,
        "SELECT table_name, string_agg(column_name, ',' ORDER BY ordinal_position) "
        "FROM information_schema.columns WHERE table_schema='public' GROUP BY table_name",
    )
    tables = {
        str(t).upper(): {x.strip().upper() for x in str(c or "").split(",") if x.strip()}
        for t, c in cols["rows"]
    }
    print(f"目标库表 {len(tables)} 张")

    async with async_db_session() as db:
        objs = (
            await db.execute(
                text(
                    "SELECT code, COALESCE(backing_table,''), datasource_id "
                    "FROM ai_ont_object WHERE is_deleted=false"
                )
            )
        ).fetchall()
        existing = {
            (str(r[0]), str(r[1]), str(r[2] or ""))
            for r in (
                await db.execute(
                    text(
                        "SELECT source_object, target_object, COALESCE(source_field,'') "
                        "FROM ai_ont_link WHERE is_deleted=false"
                    )
                )
            ).fetchall()
        }

    # 1) 回填 datasource_id：支撑表命中目标库表名、且当前未打标（或标错）
    retag = [
        c for c, bt, dsd in objs
        if bt and str(bt).upper() in tables and dsd != DS_ID
    ]
    print(f"待回填 datasource_id={DS_ID} 的对象: {len(retag)}")

    # 2) 真实外键 → 关系边
    obj_by_table = {
        str(bt).upper(): c for c, bt, _ in objs
        if bt and str(bt).upper() in tables
    }
    fks = await _ex.execute_select(
        cfg,
        "SELECT tc.table_name, kcu.column_name, ccu.table_name, ccu.column_name "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON kcu.constraint_name=tc.constraint_name AND kcu.table_schema=tc.table_schema "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON ccu.constraint_name=tc.constraint_name AND ccu.table_schema=tc.table_schema "
        "WHERE tc.constraint_type='FOREIGN KEY'",
    )
    todo = []
    for src_t, src_c, tgt_t, tgt_c in fks["rows"]:
        s, t = str(src_t).upper(), str(tgt_t).upper()
        so, to = obj_by_table.get(s), obj_by_table.get(t)
        if not (so and to):
            continue
        key = (so, to, str(src_c))
        if key in existing:
            continue
        todo.append({
            "source_object": so, "target_object": to,
            "name": f"{s} → {t}", "card": "many_to_one",
            "source_field": str(src_c), "target_field": str(tgt_c),
            "join_method": "foreign_key",
            "description": "来自目标库真实外键约束",
        })
    print(f"待补真实外键关系边: {len(todo)}")

    if dry:
        print("\n[dry-run] 未写入")
        return

    if retag:
        async with async_db_session.begin() as db:
            await db.execute(
                text(
                    "UPDATE ai_ont_object SET datasource_id=:d "
                    "WHERE is_deleted=false AND code = ANY(:codes)"
                ),
                {"d": DS_ID, "codes": retag},
            )
        print(f"已回填 {len(retag)} 个对象的 datasource_id={DS_ID}")

    ok = 0
    for p in todo:
        try:
            await upsert_link(p)
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"  !! 写入失败 {p['name']}: {str(e)[:100]}")
    print(f"已补关系边 {ok} 条")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.dry_run))
