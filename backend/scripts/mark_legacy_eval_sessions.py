"""一次性清理：把「评测隔离上线之前」产生的自动化会话标记为 is_eval=true。

背景：`is_eval` 是 2026-11 才加的隔离字段。此前评测/基准都在同一条 `ask` 链路上跑，
把题库与基准题写进了用户的问数历史（实测同一道题重复 50~85 次，使用统计也被污染）。

识别口径（保守，三选一命中即算）：
1. `title == left(题库问题, 30)` —— `ask` 建会话时用 `question[:30]` 当标题；
2. `title == left(基准题面, 30)` —— 旧 `benchmark.py` 的 GOLDEN / NL2SQL_GOLDEN；
3. `title == 指标名` 且同名会话 **≥3 次**（旧基准的题面就是指标名，如「今日告警数」）。
另外要求会话消息数 ≤ ``--max-msgs``（默认 2），避免误伤多轮追问。

用法::

    cd backend
    uv run python scripts/mark_legacy_eval_sessions.py            # 干跑
    uv run python scripts/mark_legacy_eval_sessions.py --apply    # 执行（可回滚）
    uv run python scripts/mark_legacy_eval_sessions.py --revert <备份文件>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile

from sqlalchemy import text

from app.core.database import async_db_session

#: 命中口径：消息数不超过 N（自动化跑的基本是「一问一答」）
MAX_MSGS = 2


def _benchmark_titles() -> set[str]:
    """旧基准的题面前 30 字（与 `ask` 建会话时的标题截断口径一致）。"""
    try:
        from app.plugin.module_ai.query.benchmark import GOLDEN, NL2SQL_GOLDEN
    except Exception:  # noqa: BLE001
        return set()
    out: set[str] = set()
    for item in [*(GOLDEN or []), *(NL2SQL_GOLDEN or [])]:
        q = str((item or {}).get("q") or "").strip()
        if q:
            out.add(q[:30])
    return out


async def _candidates(max_msgs: int, min_repeat: int = 2) -> list[tuple]:
    async with async_db_session() as db:
        case_titles = {r[0] for r in (await db.execute(text(
            "SELECT DISTINCT left(question,30) FROM ai_query_testcase WHERE is_deleted=false"
        ))).fetchall() if r[0]}
        metric_names = {r[0] for r in (await db.execute(text(
            "SELECT name FROM ai_query_metrics WHERE is_deleted=false"
        ))).fetchall() if r[0]}
        rows = (await db.execute(text(
            """
            SELECT s.id, s.title, s.user_id, s.created_time,
                   (SELECT count(*) FROM ai_query_messages m
                     WHERE m.session_id = s.id AND m.is_deleted = false) AS msgs
            FROM ai_query_sessions s
            WHERE s.is_deleted = false AND coalesce(s.is_eval, false) = false
            ORDER BY s.id
            """
        ))).fetchall()

    bench_titles = _benchmark_titles()
    # 同名会话计数（用于「同一个题面被反复跑」判定）
    from collections import Counter

    title_counts = Counter(r[1] for r in rows)
    out = []
    for r in rows:
        sid, title, uid, created, msgs = r
        if int(msgs or 0) > max_msgs:
            continue
        # 保守门槛：同一个标题至少出现 min_repeat 次才认定为自动化。
        # 只问过一次的（很可能是真实用户）即使题面撞上题库/基准题也**不动**。
        if title_counts[title] < min_repeat:
            continue
        hit = title in case_titles or title in bench_titles
        if not hit and title in metric_names and title_counts[title] >= 3:
            hit = True
        if hit:
            out.append(r)
    return out


async def main() -> None:  # pragma: no cover - 运维脚本
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写库（默认只干跑）")
    ap.add_argument("--max-msgs", type=int, default=MAX_MSGS)
    ap.add_argument("--min-repeat", type=int, default=2, help="同一标题至少重复几次才算自动化")
    ap.add_argument("--revert", type=str, default="", help="从备份 JSON 回滚")
    args = ap.parse_args()

    if args.revert:
        with open(args.revert, encoding="utf-8") as f:
            ids = json.load(f).get("ids", [])
        if not ids:
            print("备份里没有 id")
            return
        async with async_db_session.begin() as db:
            res = await db.execute(
                text("UPDATE ai_query_sessions SET is_eval=false WHERE id = ANY(:ids)"),
                {"ids": ids},
            )
        print(f"已回滚 {res.rowcount} 条会话（is_eval=false）")
        return

    cand = await _candidates(args.max_msgs, args.min_repeat)
    ids = [int(r[0]) for r in cand]
    print(f"命中自动化会话 {len(ids)} 条（消息数 ≤ {args.max_msgs}）")
    for r in cand[:8]:
        print(f"  样例 #{r[0]} | {r[1]} | user={r[2]} | msgs={r[4]} | {r[3]}")
    if not args.apply:
        print("\n（干跑）加 --apply 才会写库；执行前会写备份文件。")
        return

    backup = os.path.join(tempfile.gettempdir(), "legacy_eval_session_ids.json")
    with open(backup, "w", encoding="utf-8") as f:
        json.dump({"ids": ids}, f, ensure_ascii=False)
    async with async_db_session.begin() as db:
        res = await db.execute(
            text("UPDATE ai_query_sessions SET is_eval=true WHERE id = ANY(:ids)"),
            {"ids": ids},
        )
    print(f"已标记 {res.rowcount} 条自动化会话（is_eval=true）")
    print(f"备份（用于回滚）：{backup}")


asyncio.run(main())
