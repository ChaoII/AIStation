"""
补充已有布局数据的模板/轮巡/描述字段
用法: uv run python scripts/seed_layouts.py
"""
import asyncio

import asyncpg

SAMPLES = [
    (True, 30, "主监控室默认4路分割布局，轮巡周期30秒"),
    (False, 15, "仓库区域9路全景监控，快速轮巡"),
    (True, None, "单路全屏显示入口摄像机"),
    (True, 60, "6路重点设备监控，含主画面放大"),
    (False, 20, "停车场16路密集监控"),
    (True, 10, "13路布局，中间4格合并显示重点区域"),
]


async def seed():
    conn = await asyncpg.connect(
        host="localhost", port=5432, user="root",
        password="ServBay.dev", database="fastapiadmin",
    )
    try:
        rows = await conn.fetch(
            "SELECT id FROM video_layouts WHERE is_deleted = false ORDER BY id"
        )
        updated = 0
        for i, row in enumerate(rows):
            tpl, patrol, desc = SAMPLES[i % len(SAMPLES)]
            await conn.execute(
                """UPDATE video_layouts SET
                   is_template = $1, patrol_interval = $2, description = $3
                   WHERE id = $4""",
                tpl, patrol, desc, row["id"],
            )
            updated += 1
        print(f"✅ 已更新 {updated}/{len(rows)} 条布局记录")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
