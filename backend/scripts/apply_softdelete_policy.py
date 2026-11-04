"""把金标统一到「业务数据默认排除软删除」口径。

为什么需要（2026-11 实测）
--------------------------
78 道启用题里，涉及有 `ISDELETED` 列的表共 57 道：
    9 道金标写了 `ISDELETED` 条件（其中 6 道问的就是"已删除"，应当保留）
    48 道完全没写
结果同义题给出两个答案：

    入厂煤批次里矿点名称不为空的占比              → 7.94（不过滤）
    入厂煤批次里矿点名称既不是空字符串也不是 NULL → 9.91（过滤）

模型答 7.94 被判错，而它答的是另一道同名题的正确答案 → 金标自相矛盾。

本脚本只做一件事：给"没问删除、但表有 `ISDELETED`"的金标补上
`"ISDELETED" = false`。**不碰**问删除的题；注入不了的（异常结构）单列出来人工看。

用法::

    cd backend
    uv run python scripts/apply_softdelete_policy.py            # 预览
    uv run python scripts/apply_softdelete_policy.py --apply    # 写库

安全措施：每条新 SQL 都要**真的跑一遍且返回非空**才允许写入；失败即跳过并打印原因。
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from app.core.database import async_db_session
from app.plugin.module_ai.query import executor as _ex

DATASOURCE_ID = 4
DATASET = "fuel-v2"

#: 问题本身就在问"删除"的：必须保留原意，不做统一（与运行时同源）
from app.plugin.module_ai.query.softdelete import asks_about_deletion as _asks_del  # noqa: E402


def _inject(sql: str, del_tables: set[str]) -> tuple[str | None, str]:
    """调用**运行时同一套**实现（softdelete.inject_softdelete），避免两份逻辑漂移。"""
    from app.plugin.module_ai.query.softdelete import inject_softdelete

    new_sql, hit = inject_softdelete(sql, del_tables)
    if not hit:
        return None, "无软删表"
    return new_sql, "ok"


async def main() -> None:  # pragma: no cover - 运维脚本
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写库（默认只预览）")
    args = ap.parse_args()

    async with async_db_session() as db:
        ds = (await db.execute(text(
            "SELECT type,host,port,database,username,password "
            "FROM ai_query_datasources WHERE id=:i"), {"i": DATASOURCE_ID})).fetchone()
        cases = (await db.execute(text(
            "SELECT id, question, gold_sql FROM ai_query_testcase "
            "WHERE is_deleted=false AND dataset=:d AND enabled=true ORDER BY id"),
            {"d": DATASET})).fetchall()
    if not ds:
        raise SystemExit(f"数据源 {DATASOURCE_ID} 不存在")
    cfg = {"type": ds[0], "host": ds[1], "port": ds[2], "database": ds[3],
           "username": ds[4], "password": ds[5]}

    import sqlglot
    from sqlglot import exp

    # 数据源里哪些表有 ISDELETED 列（以同步下来的 schema 为准）
    async with async_db_session() as db:
        sch = (await db.execute(text(
            "SELECT table_name, columns::text FROM ai_query_schema WHERE datasource='ds:4'"))).fetchall()
    del_tables = {(t or "").upper() for t, c in sch if "ISDELETED" in (c or "").upper()}

    todo: list[tuple[int, str, str]] = []
    for cid, q, gold in cases:
        g = gold or ""
        if not g.strip():
            continue
        tables = {t.name.upper() for t in sqlglot.parse_one(g, read="postgres").find_all(exp.Table)}
        if not (tables & del_tables):
            continue
        if "ISDELETED" in g.replace(" ", "").upper():
            continue
        if _asks_del(q):
            continue
        todo.append((cid, q, g))

    print(f"候选 {len(todo)} 道（有软删表、金标没过滤、问的不是删除）\n")
    updates: list[tuple[int, str, str, str]] = []
    changed: list[bool] = []
    for cid, q, g in todo:
        patched, why = _inject(g, del_tables)
        if patched is None:
            print(f"  [跳过] {q[:40]} —— {why}")
            continue
        try:
            before = await _ex.execute_select(cfg, g)
            after = await _ex.execute_select(cfg, patched)
        except Exception as e:  # noqa: BLE001
            print(f"  [跳过] {q[:40]} —— 新 SQL 执行失败：{str(e)[:70]}")
            continue
        if not (after.get("rows") or []):
            print(f"  [跳过] {q[:40]} —— 新 SQL 返回空")
            continue
        va = (before["rows"] or [[]])[0]
        vb = (after["rows"] or [[]])[0]
        # 标记用 ASCII：这份输出经常被重定向到文件再做 grep，
        # 中文在 Windows 下会被按 GBK 重编码，grep 直接失效（实测踩过）。
        mark = "CHG " if va != vb else "SAME"
        changed.append(va != vb)
        print(f"  [{mark}] {q[:40]}\n           {str(va)[:60]} -> {str(vb)[:60]}")
        updates.append((cid, q, g, patched))

    print(f"\nUPDATABLE {len(updates)}  CHANGED {sum(changed)}")
    if not args.apply:
        print("\n（预览模式；--apply 写库）")
        return
    if not updates:
        return
    async with async_db_session.begin() as db:
        for cid, _q, _g, patched in updates:
            await db.execute(
                text("UPDATE ai_query_testcase SET gold_sql=:s, updated_time=now() "
                     "WHERE id=:i"), {"s": patched, "i": cid})
    print(f"\n已写库 {len(updates)} 道（dataset={DATASET}）")


if __name__ == "__main__":
    asyncio.run(main())
