"""把 ds:4（燃料库）来源、但没有归属域的本体对象挂到 fuel_business 域。

背景：图谱按「域」过滤（对象 + 两端都在域内的关系）。燃料库导入时对象没写
domain_code，303 个对象里有 300 个属于 ds:4 —— 选中「燃煤业务库」后这些对象
和它们的 214 条关系全被过滤掉，表现就是"图上一条关系都没有"。

用法::

    python scripts/assign_ontology_domain.py            # 预览
    python scripts/assign_ontology_domain.py --apply    # 写库
"""

import argparse
import asyncio

from sqlalchemy import text

from app.core.database import async_db_session

DS = "ds:4"
DOMAIN = "fuel_business"

SQL_TARGETS = """
SELECT o.id, o.code
FROM ai_ont_object o
WHERE o.is_deleted = false
  AND coalesce(o.domain_code, '') = ''
  AND EXISTS (
      SELECT 1 FROM ai_query_schema s
      WHERE s.datasource = :ds
        AND upper(s.table_name) = upper(coalesce(nullif(o.backing_table, ''), 'ont_' || o.code))
  )
ORDER BY o.code
"""


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    async with async_db_session() as db:
        rows = (await db.execute(text(SQL_TARGETS), {"ds": DS})).fetchall()
        dom = (await db.execute(text(
            "SELECT code, name FROM ai_ont_domain WHERE code=:c AND is_deleted=false"),
            {"c": DOMAIN})).fetchone()
    if not dom:
        raise SystemExit(f"域 {DOMAIN} 不存在")
    print(f"目标域 {dom[0]}（{dom[1]}）；待挂接对象 {len(rows)} 个")
    for _id, code in rows[:8]:
        print("   ", code)
    if not args.apply:
        print("\n（预览模式；--apply 写库）")
        return
    async with async_db_session.begin() as db:
        await db.execute(text(
            "UPDATE ai_ont_object SET domain_code=:d, updated_time=now() "
            "WHERE id = ANY(:ids)"), {"d": DOMAIN, "ids": [r[0] for r in rows]})
    print(f"\n已挂接 {len(rows)} 个对象到 {DOMAIN}")


asyncio.run(main())
