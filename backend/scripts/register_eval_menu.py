"""注册「问数评测」菜单（/ai/eval）到 sys_menu，并授权给 admin 角色。

⚠️ 已废弃（2026-10-15）：被 backend/app/scripts/init_app.py 的 _ensure_ai_menus
幂等逻辑取代（问数评测已并入「智能问数」工作台），请勿再运行，避免把旧菜单写回。

用法（backend 下）::

    python scripts/register_eval_menu.py --dry-run   # 只看现状与将要插入的内容
    python scripts/register_eval_menu.py             # 真正写入

幂等：已存在同 route_path 的菜单则跳过插入（但仍会补授权）。
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

ROUTE_PATH = "/ai/eval"
ROUTE_NAME = "AiEval"
MENU_NAME = "问数评测"
COMPONENT = "module_ai/eval/index"
PERMISSION = "module_ai:query:ask"


async def main(dry: bool) -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session

    # 写入必须用 .begin()（否则事务不提交，脚本"看起来成功"但库里没有）
    async with async_db_session.begin() as db:
        rows = (
            await db.execute(
                text(
                    'SELECT id, parent_id, type, name, route_path, component_path, "order", hidden '
                    "FROM sys_menu WHERE route_path LIKE '/ai%' ORDER BY parent_id NULLS FIRST, \"order\""
                )
            )
        ).fetchall()
        print("=== 现有 /ai* 菜单 ===")
        for r in rows:
            print(f"  id={r[0]} parent={r[1]} type={r[2]} name={r[3]} path={r[4]} comp={r[5]} order={r[6]} hidden={r[7]}")

        parent = next((r for r in rows if r[4] in ("/ai", "/ai/overview") and r[1] is None), None)
        if parent is None:
            parent = next((r for r in rows if r[4] == "/ai"), None)
        if parent is None:
            print("!! 找不到 /ai 父菜单，无法自动挂载。请先确认 AI 菜单已创建。")
            return
        print(f"\n将挂到父菜单：id={parent[0]} name={parent[3]} path={parent[4]}")

        exists = (
            await db.execute(
                text("SELECT id FROM sys_menu WHERE route_path=:p AND is_deleted=false"),
                {"p": ROUTE_PATH},
            )
        ).fetchone()

        if exists:
            menu_id = exists[0]
            print(f"已存在菜单 id={menu_id}（{ROUTE_PATH}），跳过插入")
        else:
            print(f"将插入：name={MENU_NAME} path={ROUTE_PATH} comp={COMPONENT}")
            if dry:
                menu_id = None
            else:
                max_order = (
                    await db.execute(
                        text('SELECT COALESCE(MAX("order"),0) FROM sys_menu WHERE parent_id=:p'),
                        {"p": parent[0]},
                    )
                ).scalar() or 0
                row = (
                    await db.execute(
                        text(
                            'INSERT INTO sys_menu(name,type,"order",permission,route_name,route_path,'
                            "component_path,hidden,keep_alive,always_show,title,affix,client,parent_id,"
                            "status,uuid,is_deleted,created_time,updated_time) "
                            "VALUES(:n,2,:o,:perm,:rn,:rp,:cp,false,true,false,:t,false,'pc',:pid,"
                            "'0',:uuid,false,now(),now()) RETURNING id"
                        ),
                        {
                            "n": MENU_NAME, "o": max_order + 1, "perm": PERMISSION,
                            "rn": ROUTE_NAME, "rp": ROUTE_PATH, "cp": COMPONENT,
                            "t": MENU_NAME, "pid": parent[0],
                            "uuid": __import__("uuid").uuid4().hex,
                        },
                    )
                ).fetchone()
                menu_id = row[0]
                print(f"已插入菜单 id={menu_id}")

        if menu_id is None:
            print("\n[dry-run] 未写入任何数据")
            return

        # 授权给 admin 角色（superadmin 角色 code=admin）
        role = (
            await db.execute(
                text(
                    "SELECT id, name, code FROM sys_role"
                    " WHERE LOWER(code)='admin' AND is_deleted=false ORDER BY id LIMIT 1"
                )
            )
        ).fetchone()
        if role is None:
            print("!! 找不到 code=admin 的角色，请手工在「角色管理」里勾选该菜单")
            return
        bound = (
            await db.execute(
                text(
                    "SELECT 1 FROM sys_role_menus WHERE role_id=:r AND menu_id=:m"
                ),
                {"r": role[0], "m": menu_id},
            )
        ).fetchone()
        if bound:
            print(f"角色 {role[1]}({role[2]}) 已绑定该菜单，跳过")
        elif dry:
            print(f"[dry-run] 将把菜单 id={menu_id} 授权给角色 {role[1]}")
        else:
            await db.execute(
                text("INSERT INTO sys_role_menus(role_id, menu_id) VALUES (:r,:m)"),
                {"r": role[0], "m": menu_id},
            )
            print(f"已授权给角色 {role[1]}({role[2]})")

    print("\n完成。前端需**重新登录**（或在菜单管理里刷新）才会看到新菜单。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.dry_run))
