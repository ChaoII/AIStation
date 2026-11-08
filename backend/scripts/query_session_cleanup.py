"""清理问数会话里**自动化留下的垃圾**（软删，可回滚）。

背景（2026-11-08 实测）：dev 库里 `ai_query_sessions` 有 14,026 条未删除会话，其中
13,545 条是评测跑出来的（`is_eval=true`），另有 400+ 条是冒烟/探测脚本单条提问留下的
（只有 1 条消息，正常 UI 对话至少 user+assistant 两条）。这些会话会把左侧「会话」列表
淹掉（实测列表里同一句问题出现 37 次）。

判定口径（两条，都要求早于 `--days` 天，避免误删刚产生的东西）：

1. `is_eval = true`：评测上下文写入，UI 列表本来就过滤它，属于纯垃圾；
2. `is_eval` 非真 且 消息数 <= 1：脚本直接调服务/接口留下的一次性会话；真实 UI 对话
   至少有 2 条消息，所以用 1 条做界。

**软删**（`is_deleted=true`），消息同步软删；不物理删除，随时可回滚：
`UPDATE ai_query_sessions SET is_deleted=false WHERE deleted_time >= '<本次时间>'`。

用法：
    python scripts/query_session_cleanup.py --dry-run
    python scripts/query_session_cleanup.py --apply
    python scripts/query_session_cleanup.py --apply --days 7 --user 1
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))

from sqlalchemy import text as T  # noqa: E402

from app.core.database import async_db_session  # noqa: E402

#: 会话「只有一条消息」即视为脚本产物（真实 UI 对话至少 user + assistant 两条）。
_SINGLETON_SQL = (
    "(SELECT count(*) FROM ai_query_messages m "
    "WHERE m.session_id = s.id AND m.is_deleted = false) <= 1"
)


async def main(dry: bool, days: int, user_id: int | None) -> None:
    cutoff = datetime.now() - timedelta(days=days)
    user_cond = " AND s.user_id = :uid" if user_id else ""
    params: dict = {"cut": cutoff}
    if user_id:
        params["uid"] = user_id

    eval_cond = f"s.is_deleted = false AND s.is_eval = true AND s.created_time < :cut{user_cond}"
    single_cond = (
        "s.is_deleted = false AND (s.is_eval IS NOT TRUE) AND s.created_time < :cut"
        f"{user_cond} AND {_SINGLETON_SQL}"
    )

    async with async_db_session() as db:
        eval_ids = [
            r[0]
            for r in (await db.execute(T(f"SELECT s.id FROM ai_query_sessions s WHERE {eval_cond}"), params)).fetchall()
        ]
        single_ids = [
            r[0]
            for r in (await db.execute(T(f"SELECT s.id FROM ai_query_sessions s WHERE {single_cond}"), params)).fetchall()
        ]

    ids = sorted(set(eval_ids) | set(single_ids))
    print(f"评测会话 {len(eval_ids)} 条；单条消息会话 {len(single_ids)} 条；合计去重 {len(ids)} 条（早于 {cutoff:%Y-%m-%d %H:%M}）")
    if not ids or dry:
        print("[预演] 未写库" if ids else "没有需要清理的会话")
        return

    now = datetime.now()
    deleted_sessions = deleted_messages = 0
    async with async_db_session.begin() as db:
        for i in range(0, len(ids), 500):
            chunk = ids[i : i + 500]
            deleted_messages += (
                await db.execute(
                    T(
                        "UPDATE ai_query_messages SET is_deleted = true, deleted_time = :now "
                        "WHERE is_deleted = false AND session_id = ANY(:ids)"
                    ),
                    {"now": now, "ids": chunk},
                )
            ).rowcount
            deleted_sessions += (
                await db.execute(
                    T(
                        "UPDATE ai_query_sessions SET is_deleted = true, deleted_time = :now "
                        "WHERE is_deleted = false AND id = ANY(:ids)"
                    ),
                    {"now": now, "ids": chunk},
                )
            ).rowcount
    print(f"[已落地] 软删会话 {deleted_sessions} 条、消息 {deleted_messages} 条")
    print(f"回滚：UPDATE ai_query_sessions SET is_deleted=false WHERE deleted_time >= '{now:%Y-%m-%d %H:%M:%S}'")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--days", type=int, default=1, help="只清理早于 N 天的会话（默认 1）")
    ap.add_argument("--user", type=int, default=None, help="只清理某个用户（默认全部）")
    a = ap.parse_args()
    if not a.dry_run and not a.apply:
        print("请显式指定 --dry-run 或 --apply")
        raise SystemExit(2)
    asyncio.run(main(not a.apply, a.days, a.user))
