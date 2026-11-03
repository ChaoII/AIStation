"""接线审计：前端页面 ↔ 菜单 component_path 是否一一对应（找孤儿页/缺失页）。"""

from __future__ import annotations

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


async def main() -> None:
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session

    views = Path(__file__).resolve().parents[2] / "frontend" / "src" / "views"
    # 页面集合：module_ai 下的 *.vue，**排除 components/**，并归一掉结尾的 /index
    pages: set[str] = set()
    for p in views.rglob("*.vue"):
        s = str(p)
        if "module_ai" not in s or f"{os.sep}components{os.sep}" in s:
            continue
        rel = str(p.relative_to(views)).replace("\\", "/")[:-4]
        pages.add(rel[: -len("/index")] if rel.endswith("/index") else rel)

    async with async_db_session() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT component_path, route_path, name, hidden FROM sys_menu "
                    "WHERE is_deleted=false AND component_path LIKE 'module_ai/%' "
                    "ORDER BY component_path"
                )
            )
        ).fetchall()
    menu: dict[str, tuple[str, str, bool]] = {}
    for r in rows:
        cp = str(r[0]).strip()
        if not cp:
            continue
        key = cp[: -len("/index")] if cp.endswith("/index") else cp
        menu[key] = (str(r[1]), str(r[2]), bool(r[3]))

    print(f"前端 AI 页面 {len(pages)} 个；菜单登记的 component_path {len(menu)} 个")
    orphan_pages = sorted(pages - set(menu))
    missing_pages = sorted(set(menu) - pages)
    print(f"\n=== 有页面但**没有菜单**（用户点不到）: {len(orphan_pages)} ===")
    for p in orphan_pages:
        print("  ", p)
    print(f"\n=== 有菜单但**页面不存在**（点了会白屏）: {len(missing_pages)} ===")
    for m in missing_pages:
        rp, nm, hid = menu[m]
        print(f"   {m}  route={rp} name={nm} hidden={hid}")
    print("\n=== 与问数相关的菜单（含 hidden）===")
    for m, (rp, nm, hid) in sorted(menu.items()):
        if "query" in m or "eval" in m:
            print(f"   {m:42s} route={rp:22s} name={nm} hidden={hid}")


asyncio.run(main())
