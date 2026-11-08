"""把每个非超管用户的「旧可查范围」落成显式 allow（不改变现状的迁移）。

与 backfill 的 legacy_default_allow 区别：那个只发给"没有域/ABAC"的用户；
这里发给**所有人**，保证切 enforce 当天权限与 legacy 完全一致。
名称前缀 legacy-keep-，可按前缀整体删除（收窄时用）。

用法：python scripts/query_policy_grant_legacy.py [--dry-run]
"""
import argparse
import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, r"D:\AIStation\backend")
os.environ.setdefault("ENVIRONMENT", "dev")
from main import create_app  # noqa: E402

create_app()

from sqlalchemy import text as T  # noqa: E402

from app.core.database import async_db_session  # noqa: E402


async def main(dry: bool) -> None:
    from app.plugin.module_ai.query.service import AiQueryService as S

    async with async_db_session() as db:
        users = (await db.execute(T(
            "SELECT id, username FROM sys_user "
            "WHERE is_deleted=false AND status='0' AND is_superuser=false ORDER BY id"))).fetchall()

    total = 0
    for uid, name in users:
        allowed = await S._allowed_for_user(SimpleNamespace(
            user=SimpleNamespace(id=uid, is_superuser=False)))
        if not allowed:
            continue
        rows = 0
        if not dry:
            async with async_db_session.begin() as db:
                for table in sorted(allowed):
                    exists = (await db.execute(T(
                        "SELECT 1 FROM ai_policy WHERE name='legacy-keep' "
                        "AND resource_code=:r AND subject_kind='user' AND subject_value=:u "
                        "AND is_deleted=false LIMIT 1"),
                        {"r": table, "u": str(uid)})).fetchone()
                    if exists:
                        continue
                    await db.execute(T(
                        "INSERT INTO ai_policy(name,description,effect,resource_kind,resource_code,"
                        "subject_kind,subject_value,condition,columns,mask_expr,marking,priority,enabled) "
                        "VALUES('legacy-keep','切 enforce 前保留旧范围；收窄时按 name 删除','allow','table',"
                        ":r,'user',:u,'','[]','','',1,true)"),
                        {"r": table, "u": str(uid)})
                    rows += 1
        else:
            rows = len(allowed)
        total += rows
        print(f"  {name}(id={uid}): {len(allowed)} 张，新增 {rows} 条")

    print(f"{'[预演]' if dry else '[已写入]'} 合计新增 {total} 条 allow")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(main(args.dry_run))
