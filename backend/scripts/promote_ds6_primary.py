"""把 ds:6 提升为平台主数据源：默认标志 + 评测题复制。

用法：
    cd backend
    uv run python scripts/promote_ds6_primary.py
    uv run python scripts/run_eval_once.py --run-limit=105 --datasource=ds:6

幂等：默认标志直接覆盖；评测题按 (datasource,question) upsert。
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DS_CODE = "ezdcs_local"


async def main() -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session
    from main import create_app

    create_app()
    async with async_db_session.begin() as db:
        ds_id = (await db.execute(text(
            "SELECT id FROM ai_query_datasources WHERE code=:c AND is_deleted=false"
        ), {"c": DS_CODE})).scalar()
        if not ds_id:
            raise SystemExit(f"找不到数据源 {DS_CODE}")
        target = f"ds:{int(ds_id)}"
        # 1) 默认数据源：只保留 ds:6
        await db.execute(text(
            "UPDATE ai_query_datasources SET \"default\" = (code = :c) WHERE is_deleted=false"
        ), {"c": DS_CODE})
        # 2) 评测题：ds:4 → ds:6（保留全部字段；gold 在 ds:6 上现算）
        await db.execute(text(
            "INSERT INTO ai_query_testcase(question,gold_sql,datasource,difficulty,scenario,form,"
            "expected_metric,tags,verified,enabled,dataset,is_deleted,created_time,updated_time) "
            "SELECT question,gold_sql,:t,difficulty,scenario,form,expected_metric,tags,verified,"
            "enabled,dataset,false,now(),now() FROM ai_query_testcase "
            "WHERE datasource='ds:4' AND is_deleted=false "
            "ON CONFLICT (datasource,question) DO UPDATE SET "
            "gold_sql=EXCLUDED.gold_sql, difficulty=EXCLUDED.difficulty, scenario=EXCLUDED.scenario, "
            "form=EXCLUDED.form, expected_metric=EXCLUDED.expected_metric, tags=EXCLUDED.tags, "
            "enabled=EXCLUDED.enabled, dataset=EXCLUDED.dataset, updated_time=now()"
        ), {"t": target})
        n = (await db.execute(text(
            "SELECT count(*) FROM ai_query_testcase WHERE datasource=:t AND is_deleted=false"
        ), {"t": target})).scalar()
    print(f"[ok] 默认数据源 = {target}；评测题已复制/更新，现有 {n} 条")
    print(f"[next] uv run python scripts/run_eval_once.py --run-limit=105 --datasource={target}")


if __name__ == "__main__":
    asyncio.run(main())
