"""查「智能助手(Chat)」菜单到底在哪、是否可见（回答"点不到"到底指什么）。"""

from __future__ import annotations

import asyncio
import json
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
                    "SELECT id, parent_id, name, route_name, route_path, component_path, "
                    "hidden, type, permission FROM sys_menu WHERE is_deleted=false "
                    "AND (route_name='Chat' OR component_path LIKE '%chat%')"
                )
            )
        ).fetchall()
        print("=== Chat 相关菜单 ===")
        for r in rows:
            print(json.dumps({"id": r[0], "parent": r[1], "name": r[2], "route_name": r[3],
                              "route_path": r[4], "component_path": r[5], "hidden": r[6],
                              "type": r[7], "permission": r[8]}, ensure_ascii=True))
        pids = sorted({r[1] for r in rows if r[1]})
        if pids:
            prs = (
                await db.execute(
                    text("SELECT id, name, hidden, type, route_path FROM sys_menu "
                         "WHERE id = ANY(:ids)"),
                    {"ids": pids},
                )
            ).fetchall()
            print("=== 它们的父菜单 ===")
            for p in prs:
                print(json.dumps({"id": p[0], "name": p[1], "hidden": p[2], "type": p[3],
                                  "route_path": p[4]}, ensure_ascii=True))
        else:
            print("=== 它们的父菜单：无（parent_id 为空 = 顶层）===")
        # 页面文件是否存在
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "views"
        for cand in ("module_ai/chat/index.vue", "module_ai/chat.vue"):
            print(f"页面 {cand} 存在 = {(root / cand).exists()}")


asyncio.run(main())
