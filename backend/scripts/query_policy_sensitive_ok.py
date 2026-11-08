"""把 ai_access_rule.sensitive_ok 迁成「角色可见指定敏感列」的 allow。

引擎规则：**更具体主体**的列级 allow 可以覆盖 everyone 级列 deny（表级 deny 不可覆盖）。
用法：python scripts/query_policy_sensitive_ok.py --dry-run|--apply
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, r"D:\AIStation\backend")
os.environ.setdefault("ENVIRONMENT", "dev")
from main import create_app  # noqa: E402

create_app()

from sqlalchemy import text as T  # noqa: E402

from app.core.database import async_db_session  # noqa: E402


async def main(dry: bool) -> None:
    async with async_db_session() as db:
        rules = (await db.execute(T(
            "SELECT id, value FROM ai_access_rule "
            "WHERE enabled=true AND sensitive_ok=true AND attribute='role' AND is_deleted=false"
        ))).fetchall()
        cols = (await db.execute(T(
            "SELECT table_name, column_name FROM ai_query_asset_columns "
            "WHERE sensitive=true AND is_deleted=false ORDER BY table_name"
        ))).fetchall()

    if not rules:
        print("没有 sensitive_ok 规则，无需迁移")
        return
    if not cols:
        print("没有敏感列，无需迁移")
        return

    by_table: dict[str, list[str]] = {}
    for table, column in cols:
        by_table.setdefault(table, []).append(column)

    total = 0
    for rid, role in rules:
        added = 0
        for table, columns in by_table.items():
            exists = False
            if not dry:
                async with async_db_session() as db:
                    exists = bool((await db.execute(T(
                        "SELECT 1 FROM ai_policy WHERE name='sensitive-ok' AND resource_code=:r "
                        "AND subject_kind='role' AND subject_value=:s AND is_deleted=false LIMIT 1"),
                        {"r": table, "s": str(role)})).fetchone())
            if exists:
                continue
            if not dry:
                async with async_db_session.begin() as db:
                    await db.execute(T(
                        "INSERT INTO ai_policy(name,description,effect,resource_kind,resource_code,"
                        "subject_kind,subject_value,condition,columns,mask_expr,marking,priority,enabled) "
                        "VALUES('sensitive-ok','规则 sensitive_ok 迁移：该角色可见敏感列','allow','table',:r,"
                        "'role',:s,'',CAST(:c AS jsonb),'','',200,true)"),
                        {"r": table, "s": str(role), "c": json.dumps(columns)})
            added += 1
        total += added
        print(f"  规则#{rid} role={role}: {len(by_table)} 张表，新增 {added} 条")

    print(f"{'[预演]' if dry else '[已落地]'} 合计新增 {total} 条敏感列 allow")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not a.dry_run and not a.apply:
        print("请显式指定 --dry-run 或 --apply")
        raise SystemExit(2)
    asyncio.run(main(not a.apply))
