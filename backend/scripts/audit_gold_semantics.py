"""审计已有测试题的**金标语义一致性**：问题提到的实体，金标必须真的用到对应表。

不一致的题（金标"抄近路"）**禁用**并记录原因 —— 它们会把"模型老实联表"判成错。
用法（backend 下）::

    python scripts/audit_gold_semantics.py --datasource=ds:4 [--dry-run]
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


async def main(datasource: str, dry: bool) -> None:
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.eval_generate import (
        _entity_table_map,
        missing_entity_tables,
    )
    from app.plugin.module_ai.query.eval_set import list_cases

    ent = await _entity_table_map(datasource)
    print(f"实体词映射 {len(ent)} 条（如 {list(ent.items())[:3]}）")

    cases = await list_cases(datasource=datasource)
    bad: list[tuple[int, str, list[str]]] = []
    for c in cases:
        miss = missing_entity_tables(c["question"], c["gold_sql"], ent)
        if miss:
            bad.append((c["id"], c["question"], miss))
    print(f"{datasource} 共 {len(cases)} 题，其中**金标缺实体表** {len(bad)} 题")
    for i, q, miss in bad[:12]:
        print(f"  #{i} {q[:44]} → 缺 {miss}")

    if dry or not bad:
        print("\n[dry-run] 未改动" if dry else "无需改动")
        return
    async with async_db_session.begin() as db:
        for i, _q, miss in bad:
            await db.execute(
                text(
                    "UPDATE ai_query_testcase SET enabled=false, "
                    "notes='gold_missing_entity:' || :m, updated_time=now() WHERE id=:i"
                ),
                {"i": i, "m": ",".join(miss)},
            )
    print(f"\n已禁用 {len(bad)} 题（原因写入 notes，可用 enabled=true 恢复）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasource", default="ds:4")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.datasource, a.dry_run))
