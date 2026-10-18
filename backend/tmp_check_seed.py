import asyncio
import os
import sys

os.environ["ENVIRONMENT"] = "dev"
sys.path.insert(0, ".")

from app.config.setting import settings as s

dsn = f"postgresql://{s.DATABASE_USER}:{s.DATABASE_PASSWORD}@{s.DATABASE_HOST}:{s.DATABASE_PORT}/{s.DATABASE_NAME}"


async def main():
    import asyncpg

    conn = await asyncpg.connect(dsn)
    print("=== ai_skills（技能广场）===")
    rows = await conn.fetch(
        "select id,name,category,skill_type,enabled,icon,featured,install_count from ai_skills where is_deleted=false order by id"
    )
    for r in rows:
        print(dict(r))
    print("count:", len(rows))

    print("\n=== ai_tools source=agno ===")
    rows2 = await conn.fetch(
        "select id,name,kind,source,enabled from ai_tools where source='agno' and is_deleted=false order by id"
    )
    for r in rows2:
        print(dict(r))
    print("count:", len(rows2))

    print("\n=== ai_market_items ===")
    print("count:", await conn.fetchval("select count(*) from ai_market_items"))
    print("\n=== ai_plugins ===")
    for r in await conn.fetch("select key,label,executor_ready,enabled from ai_plugins where is_deleted=false"):
        print(dict(r))
    await conn.close()


asyncio.run(main())
