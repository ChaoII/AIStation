"""按域/ABAC 收窄 legacy-keep：删除超出新模型范围的保留行。

用法：
    python scripts/query_policy_narrow.py                 # 预演全部非超管
    python scripts/query_policy_narrow.py --apply         # 落地
    python scripts/query_policy_narrow.py --user 4 --apply

规则：
- 用户属于数据域 → 范围 = 域表集合（与 legacy 的域隔离语义一致）；
- 否则有命中角色的 ABAC 规则 → 范围 = 规则 allowed_tables 并集；
- 两者都没有 → **不动**（保持旧范围，避免误锁）。
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


async def main(dry: bool, only_user: int | None) -> None:
    from app.plugin.module_ai.query.service import AiQueryService as S

    async with async_db_session() as db:
        users = (await db.execute(T(
            "SELECT id, username FROM sys_user "
            "WHERE is_deleted=false AND status='0' AND is_superuser=false ORDER BY id"))).fetchall()
        if only_user:
            users = [u for u in users if u[0] == only_user]

    total = 0
    for uid, name in users:
        legacy = await S._allowed_for_user(SimpleNamespace(
            user=SimpleNamespace(id=uid, is_superuser=False)))
        domain = await S._domain_tables_for_user(uid)
        scope = set(domain) if domain else set()
        if not scope:
            roles = await S._user_role_codes_by_id(uid)
            for r in await S.list_access_rules():
                if r["enabled"] and r["attribute"] == "role" and r["value"] in roles:
                    scope |= set(r["allowed_tables"] or [])
        if not scope:
            print(f"  {name}(id={uid}): 无域/无 ABAC → 保持 {len(legacy)} 张，不动")
            continue
        surplus = sorted(legacy - scope)
        keep = len(legacy & scope)
        print(f"  {name}(id={uid}): 保留 {keep}，收窄 {len(surplus)}"
              + ("" if dry else "（已删除）"))
        if not dry and surplus:
            async with async_db_session.begin() as db:
                for table in surplus:
                    await db.execute(T(
                        "DELETE FROM ai_policy WHERE name='legacy-keep' "
                        "AND resource_code=:r AND subject_kind='user' AND subject_value=:u"),
                        {"r": table, "u": str(uid)})
        total += len(surplus)

    print(f"{'[预演]' if dry else '[已落地]'} 合计收窄 {total} 张表的保留 allow")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--user", type=int)
    a = ap.parse_args()
    if not a.dry_run and not a.apply:
        print("请显式指定 --dry-run 或 --apply")
        raise SystemExit(2)
    asyncio.run(main(not a.apply, a.user))
