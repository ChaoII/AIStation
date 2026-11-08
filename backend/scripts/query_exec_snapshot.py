"""执行层对照快照：同一组 SQL 在拆分前后必须给出同样的列/行/改写。

不依赖 LLM，只走 ``_execute_one``（权限网关 + 执行），适合每次搬移后对比。
用法：python scripts/query_exec_snapshot.py
输出格式固定（每行一条），便于 diff。
"""
from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))

from main import create_app  # noqa: E402

create_app()

CASES = [
    ("ds4_count", 'SELECT COUNT(*) AS 条数 FROM "DTXY_GYSKDGX"', "ds:4"),
    ("ds4_head", 'SELECT * FROM "DTXY_GYSKDGX" LIMIT 3', "ds:4"),
    ("system_metrics", "SELECT COUNT(*) AS 条数 FROM ai_query_metrics", "system"),
]


async def main() -> None:
    from app.plugin.module_ai.query.service import AiQueryService as S

    auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
    for name, sql, ds in CASES:
        try:
            out = await S._execute_one(sql, ds, auth, f"snapshot {name}", entry="ask")
            cols = ",".join(str(c) for c in (out.get("columns") or []))
            rows = len(out.get("rows") or [])
            applied = len(out.get("applied") or [])
            print(f"{name}\tOK\tcols={cols}\trows={rows}\tapplied={applied}")
        except Exception as e:  # noqa: BLE001
            print(f"{name}\tERR\t{str(e)[:120]}")


if __name__ == "__main__":
    asyncio.run(main())
