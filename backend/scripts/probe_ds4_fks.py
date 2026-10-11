"""探测 ds:4 的 join 线索：真外键 / 命名约定候选（生成关系边之前先取证）。"""

from __future__ import annotations

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


async def main() -> None:
    from main import create_app

    create_app()
    from app.plugin.module_ai.query import executor as _ex
    from app.plugin.module_ai.query.service import _ds_cfg_from_model, _load_ds

    ds = await _load_ds(4)
    cfg = _ds_cfg_from_model(ds)

    async def run(sql):
        return await _ex.execute_select(cfg, sql)

    # 1) 真外键
    r = await run(
        "SELECT COUNT(*) FROM information_schema.table_constraints "
        "WHERE constraint_type='FOREIGN KEY'"
    )
    print("ds:4 外键约束数:", r["rows"][0][0])

    r = await run(
        "SELECT tc.table_name, kcu.column_name, ccu.table_name AS ref_table, "
        "ccu.column_name AS ref_col "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema "
        "WHERE tc.constraint_type='FOREIGN KEY' LIMIT 15"
    )
    for row in r["rows"]:
        print("  FK:", row)

    # 2) 命名约定候选：以 ID 结尾的列，且存在同名前缀表
    r = await run(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' "
        "AND column_name LIKE '%ID' AND column_name <> 'ID'"
    )
    print("以 ID 结尾的列数:", r["rows"][0][0])

    # 3) 主键情况
    r = await run(
        "SELECT COUNT(DISTINCT table_name) FROM information_schema.table_constraints "
        "WHERE constraint_type='PRIMARY KEY' AND table_schema='public'"
    )
    print("有主键的表数:", r["rows"][0][0])
    r = await run("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
    print("public 表总数:", r["rows"][0][0])


asyncio.run(main())
