"""注册「自定义报表」菜单（/ai/query/reports）并授权给 ADMIN 角色。

幂等：已存在同 route_path 则跳过插入（仍补授权）。
用法（backend 下）::

    python scripts/register_query_reports_menu.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

ROUTE_PATH = "/ai/query/reports"
ROUTE_NAME = "AiQueryReports"
MENU_NAME = "自定义报表"
COMPONENT = "module_ai/query/reports"
PERMISSION = "module_ai:query:ask"


async def main(dry: bool) -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        parent = (
            await db.execute(
                text(
                    "SELECT id, name FROM sys_menu WHERE route_path='/ai' "
                    "AND is_deleted=false ORDER BY id LIMIT 1"
                )
            )
        ).fetchone()
        if not parent:
            print("!! 找不到 /ai 父菜单")
            return
        print(f"父菜单 id={parent[0]} {parent[1]}")

        exists = (
            await db.execute(
                text("SELECT id FROM sys_menu WHERE route_path=:p AND is_deleted=false"),
                {"p": ROUTE_PATH},
            )
        ).fetchone()
        if exists:
            menu_id = exists[0]
            print(f"已存在菜单 id={menu_id}")
        elif dry:
            print(f"[dry-run] 将插入 {MENU_NAME} {ROUTE_PATH}")
            return
        else:
            mx = (
                await db.execute(
                    text('SELECT COALESCE(MAX("order"),0) FROM sys_menu WHERE parent_id=:p'),
                    {"p": parent[0]},
                )
            ).scalar() or 0
            await db.execute(
                text(
                    'INSERT INTO sys_menu(name,type,"order",permission,route_name,route_path,'
                    "component_path,hidden,keep_alive,always_show,title,affix,client,parent_id,"
                    "status,uuid,is_deleted,created_time,updated_time) "
                    "VALUES(:n,2,:o,:perm,:rn,:rp,:cp,false,true,false,:t,false,'pc',:pid,"
                    "'0',:uuid,false,now(),now())"
                ),
                {"n": MENU_NAME, "o": mx + 1, "perm": PERMISSION, "rn": ROUTE_NAME,
                 "rp": ROUTE_PATH, "cp": COMPONENT, "t": MENU_NAME, "pid": parent[0],
                 "uuid": uuid.uuid4().hex},
            )
            menu_id = (
                await db.execute(
                    text("SELECT id FROM sys_menu WHERE route_path=:p"), {"p": ROUTE_PATH}
                )
            ).scalar()
            print(f"已插入菜单 id={menu_id}")

        role = (
            await db.execute(
                text(
                    "SELECT id, name FROM sys_role WHERE LOWER(code)='admin' "
                    "AND is_deleted=false ORDER BY id LIMIT 1"
                )
            )
        ).fetchone()
        if not role:
            print("!! 找不到 ADMIN 角色")
            return
        bound = (
            await db.execute(
                text("SELECT 1 FROM sys_role_menus WHERE role_id=:r AND menu_id=:m"),
                {"r": role[0], "m": menu_id},
            )
        ).fetchone()
        if bound:
            print(f"角色 {role[1]} 已绑定")
        else:
            await db.execute(
                text("INSERT INTO sys_role_menus(role_id, menu_id) VALUES (:r,:m)"),
                {"r": role[0], "m": menu_id},
            )
            print(f"已授权给 {role[1]}")
    print("完成（前端重新登录后可见）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.dry_run))
