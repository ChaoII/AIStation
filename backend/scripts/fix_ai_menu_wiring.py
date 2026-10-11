"""AI 菜单接线修复（幂等）：

1. **把「智能问数」设为可见** —— 它原来是 hidden，导致"存为报表"的唯一入口进不去，
   而「自定义报表」却可见 → 闭环断在菜单上；
2. **把「智能问数 / 问数评测 / 自定义报表」排到一起**（order 相邻），形成"问数"工作区；
3. **清理陈旧隐藏菜单**（component_path 指向已不存在的页面）。

用法（backend 下）::

    python scripts/fix_ai_menu_wiring.py --dry-run
    python scripts/fix_ai_menu_wiring.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

AI_PARENT_ID = 7

#: 问数工作区：route_path → order（相邻）
QUERY_WORKSPACE = {
    "/ai/query": 33,
    "/ai/eval": 34,
    "/ai/query/reports": 35,
}


def _page_exists(component_path: str) -> bool:
    if not component_path:
        return False
    views = Path(__file__).resolve().parents[2] / "frontend" / "src" / "views"
    rel = component_path.replace("/", os.sep) + ".vue"
    if (views / rel).exists():
        return True
    # `module_ai/x/index` ↔ `module_ai/x/index.vue` / `module_ai/x.vue`
    return (views / (component_path + ".vue")).exists() or (
        views / component_path.replace("/index", "") / "index.vue"
    ).exists()


async def main(dry: bool) -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT id,name,route_path,component_path,hidden FROM sys_menu "
                    "WHERE is_deleted=false AND parent_id=:p AND type=2 ORDER BY id"
                ),
                {"p": AI_PARENT_ID},
            )
        ).fetchall()

        # 1) 问数工作区：可见 + order 相邻
        for rp, order in QUERY_WORKSPACE.items():
            row = next((r for r in rows if str(r[2]) == rp), None)
            if not row:
                print(f"!! 菜单不存在：{rp}")
                continue
            if row[4]:
                print(f"  取消隐藏：{row[1]}（{rp}）")
                if not dry:
                    await db.execute(
                        text('UPDATE sys_menu SET hidden=false, "order"=:o WHERE id=:i'),
                        {"i": row[0], "o": order},
                    )
            elif row[2] != rp:
                pass
            else:
                if not dry:
                    await db.execute(
                        text('UPDATE sys_menu SET "order"=:o WHERE id=:i'),
                        {"i": row[0], "o": order},
                    )
                print(f"  已可见，仅调序：{row[1]} → order={order}")

        # 2) 清理陈旧隐藏菜单（指向不存在页面）
        stale = [
            r for r in rows
            if r[4] and r[3] and not _page_exists(str(r[3]))
        ]
        print(f"\n陈旧隐藏菜单 {len(stale)} 个：")
        for r in stale:
            print(f"  id={r[0]} {r[1]} → {r[3]}（页面已不存在）")
            if not dry:
                await db.execute(
                    text("UPDATE sys_menu SET is_deleted=true WHERE id=:i"), {"i": r[0]}
                )
        if dry:
            print("\n[dry-run] 未写入")
            return
    print("\n完成（前端重新登录后生效）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.dry_run))
