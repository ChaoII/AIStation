"""AI 菜单树 + 可达性审计：用户能从菜单点到哪些页面？哪些是"数据源/被引用方"？"""

from __future__ import annotations

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


async def main() -> None:
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT id,parent_id,type,name,route_path,component_path,hidden,\"order\" "
                    "FROM sys_menu WHERE is_deleted=false AND (parent_id=7 OR id=7) "
                    "ORDER BY \"order\", id"
                )
            )
        ).fetchall()
    print("=== AI 菜单树（父 id=7）===")
    for r in rows:
        mark = "  [隐藏]" if r[6] else ""
        print(f"  id={r[0]:4d} type={r[2]} order={r[7]:3d} {str(r[3]):14s} "
              f"{str(r[4] or '-'):26s} {str(r[5] or '-'):34s}{mark}")
    vis = [r for r in rows if r[2] == 2 and not r[6]]
    print(f"\n可见子菜单 {len(vis)} 个；隐藏 {len([r for r in rows if r[2] == 2 and r[6]])} 个")
    print("可见:", "、".join(str(r[3]) for r in vis))


asyncio.run(main())
