"""权限演示 fixture：两个用户 + 表/行/列策略 + 本体 ACL + 数据源角色限制。

用法：
    cd backend
    uv run python scripts/perm_demo_setup.py            # 创建/刷新
    uv run python scripts/perm_demo_setup.py --cleanup  # 全部删除并恢复

创建内容（全部带 `demo-perm-` / demo_ 前缀，可安全清理）：
- 角色 DEMO_ANALYST
- 用户 demo_analyst（密码 123456，复用 admin 的 bcrypt 哈希）/ demo_guest（无角色）
- 策略（subject_kind=user）：
  * analyst：6 张表 allow；批次行过滤（只看到指定供应商）；结算价格列 deny；合同表 deny
  * guest：只 allow 批次表
- ds:6 allowed_roles = [DEMO_ANALYST]（模块级：guest 进不来）
- 本体 ACL：2 个函数 + 1 个动作 + 2 个对象只对 DEMO_ANALYST 可见
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

ROLE_ANALYST = "DEMO_ANALYST"
ROLE_GUEST = "DEMO_GUEST"
USER_ANALYST = "demo_analyst"
USER_GUEST = "demo_guest"
DS_CODE = "ezdcs_local"
FUNCS = ["coal_settle_amount", "coal_ash_dry_basis"]
ACTIONS = ["coal_batch_annotate"]
OBJECTS = ["coal_batch", "coal_assay"]


async def _db():
    from app.core.database import async_db_session

    return async_db_session


async def upsert_role(code: str, name: str) -> int:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        row = (await db.execute(text("SELECT id FROM sys_role WHERE code=:c AND is_deleted=false"), {"c": code})).scalar()
        if row:
            return int(row)
        row = (await db.execute(text(
            "INSERT INTO sys_role(name,code,\"order\",data_scope,status,uuid,description,created_time,updated_time,is_deleted) "
            "VALUES (:n,:c,99,'1','0',gen_random_uuid(),'演示权限角色',now(),now(),false) RETURNING id"
        ), {"n": name, "c": code})).scalar()
        return int(row)


async def upsert_user(username: str, name: str, role_code: str | None) -> int:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        pwd = (await db.execute(text("SELECT password FROM sys_user WHERE username='admin'"))).scalar()
        uid = (await db.execute(text(
            "SELECT id FROM sys_user WHERE username=:u AND is_deleted=false"
        ), {"u": username})).scalar()
        if not uid:
            uid = (await db.execute(text(
                "INSERT INTO sys_user(username,password,name,gender,is_superuser,dept_id,uuid,status,tenant_id,"
                "created_id,updated_id,created_time,updated_time,is_deleted) "
                "VALUES (:u,:p,:n,'0',false,1,gen_random_uuid(),'0',1,1,1,now(),now(),false) RETURNING id"
            ), {"u": username, "p": pwd, "n": name})).scalar()
        uid = int(uid)
        if role_code:
            rid = (await db.execute(text("SELECT id FROM sys_role WHERE code=:c AND is_deleted=false"), {"c": role_code})).scalar()
            if rid:
                exists = (await db.execute(text(
                    "SELECT 1 FROM sys_user_roles WHERE user_id=:u AND role_id=:r"
                ), {"u": uid, "r": rid})).first()
                if not exists:
                    await db.execute(text(
                        "INSERT INTO sys_user_roles(user_id,role_id) VALUES (:u,:r)"
                    ), {"u": uid, "r": rid})
        return uid


async def reset_policies() -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        await db.execute(text("DELETE FROM ai_policy WHERE name LIKE 'demo-perm-%'"))


async def add_policy(*, name: str, table: str, effect: str, subject_value: str,
                     condition: str = "", columns: list[str] | None = None,
                     mask_expr: str = "", priority: int = 300) -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        await db.execute(text(
            "INSERT INTO ai_policy(name,description,enabled,priority,resource_kind,resource_code,"
            "effect,subject_kind,subject_value,condition,columns,mask_expr,marking,"
            "created_time,updated_time,is_deleted) "
            "VALUES (:n,'演示权限策略',true,:p,'table',:t,:e,'user',:sv,:c,:cols,:m,'',now(),now(),false)"
        ), {"n": name, "p": priority, "t": table, "e": effect, "sv": str(subject_value),
            "c": condition, "cols": json.dumps(columns or [], ensure_ascii=False), "m": mask_expr})


async def set_ds_roles() -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        await db.execute(text(
            "UPDATE ai_query_datasources SET allowed_roles=CAST(:r AS jsonb) WHERE code=:c"
        ), {"r": json.dumps([ROLE_ANALYST]), "c": DS_CODE})


async def set_acl() -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session

    codes = FUNCS + ACTIONS + OBJECTS
    async with async_db_session.begin() as db:
        await db.execute(text(
            "DELETE FROM ai_ont_resource_acl WHERE resource_code = ANY(:codes)"
        ), {"codes": codes})
        for kind, code in ([("function", c) for c in FUNCS] + [("action", c) for c in ACTIONS]
                           + [("object", c) for c in OBJECTS]):
            edit = ["DEMO_ANALYST"] if kind in ("action", "object") else []
            await db.execute(text(
                "INSERT INTO ai_ont_resource_acl(resource_kind,resource_code,view_roles,edit_roles,"
                "manage_roles,created_time) VALUES (:k,:c,CAST(:v AS jsonb),CAST(:e AS jsonb),"
                "'[]'::jsonb,now())"
            ), {"k": kind, "c": code, "v": json.dumps([ROLE_ANALYST]),
                "e": json.dumps(edit)})


async def top_supplier() -> str:
    from sqlalchemy import text

    from app.plugin.module_ai.query import executor as ex
    from app.plugin.module_ai.query import service as svc

    async with (await _db())() as db:
        ds_id = (await db.execute(text(
            "SELECT id FROM ai_query_datasources WHERE code=:c AND is_deleted=false"
        ), {"c": DS_CODE})).scalar()
    ds = await svc._load_ds(int(ds_id))
    engine = ex.build_engine(svc._ds_cfg_from_model(ds))
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            'SELECT "SUPPLIERNAME", count(*) AS c FROM "FUEL_CMCS_INFACTORYBATCH" '
            'WHERE "ISDELETED"=false AND COALESCE("SUPPLIERNAME",\'\')<>\'\' '
            "GROUP BY 1 ORDER BY c DESC LIMIT 1"
        ))).fetchone()
    return str(row[0]) if row else ""


async def cleanup() -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        await db.execute(text("DELETE FROM ai_policy WHERE name LIKE 'demo-perm-%'"))
        await db.execute(text(
            "DELETE FROM ai_ont_resource_acl WHERE resource_code = ANY(:codes)"
        ), {"codes": FUNCS + ACTIONS + OBJECTS})
        await db.execute(text(
            "UPDATE ai_query_datasources SET allowed_roles='[]'::jsonb WHERE code=:c"
        ), {"c": DS_CODE})
        for u in (USER_ANALYST, USER_GUEST):
            uid = (await db.execute(text("SELECT id FROM sys_user WHERE username=:u"), {"u": u})).scalar()
            if uid:
                await db.execute(text("DELETE FROM sys_user_roles WHERE user_id=:u"), {"u": uid})
                await db.execute(text("DELETE FROM sys_user WHERE id=:u"), {"u": uid})
        for code in (ROLE_ANALYST, ROLE_GUEST):
            await db.execute(text("DELETE FROM sys_role WHERE code=:c"), {"c": code})
    print("[cleanup] 演示用户/角色/策略/ACL/数据源角色 已清理")


async def main() -> None:
    from main import create_app

    create_app()
    if "--cleanup" in sys.argv:
        await cleanup()
        return

    await upsert_role(ROLE_ANALYST, "演示分析员")
    await upsert_role(ROLE_GUEST, "演示访客")
    analyst_uid = await upsert_user(USER_ANALYST, "演示分析员", ROLE_ANALYST)
    guest_uid = await upsert_user(USER_GUEST, "演示访客", None)
    supplier = await top_supplier()
    await reset_policies()

    # ---- 分析员：6 张表；批次行过滤；结算价格列 deny；合同表 deny ----
    for t in ("FUEL_CMCS_INFACTORYBATCH", "FUEL_CMCS_ASSAY", "FUEL_CB_COALBALANCE",
              "FUEL_CMCS_SUPPLIER", "FUEL_CMCS_MINE", "FUEL_CMCS_FUELKIND"):
        cond = ""
        if t == "FUEL_CMCS_INFACTORYBATCH" and supplier:
            cond = f"\"SUPPLIERNAME\" = '{supplier}'"
        await add_policy(name=f"demo-perm-analyst-{t.lower()}", table=t, effect="allow",
                         subject_value=str(analyst_uid), condition=cond, priority=300)
    await add_policy(name="demo-perm-analyst-denyprice", table="FUEL_CB_COALBALANCE",
                     effect="deny", subject_value=str(analyst_uid),
                     columns=["CONTRACTPRICE", "COALPRICE"], priority=350)
    await add_policy(name="demo-perm-analyst-denytable", table="FUEL_CB_COALCONTRACT",
                     effect="deny", subject_value=str(analyst_uid), priority=350)

    # ---- 访客：只有批次表 ----
    await add_policy(name="demo-perm-guest-batch", table="FUEL_CMCS_INFACTORYBATCH",
                     effect="allow", subject_value=str(guest_uid), priority=300)

    await set_ds_roles()
    await set_acl()
    print(f"[ok] analyst uid={analyst_uid} guest uid={guest_uid} supplier={supplier!r}")
    print(f"[ok] 数据源 {DS_CODE} 仅允许角色 {ROLE_ANALYST}；本体 ACL 仅该角色可见")


if __name__ == "__main__":
    asyncio.run(main())
