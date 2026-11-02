"""评测隔离：**缓存**与**配置覆盖**都不得影响全局。

两条都是实测确认过的缺陷（2026-11）：

1. ``_SQL_CACHE`` TTL 30 分钟，``_slow_path`` 一进来就查它。评测走同一个
   ``ask`` 通道，于是「跑一遍 → 改配置 → 30 分钟内再跑」时**每道题都回放上一轮
   的 SQL**，两次结果必然一样 —— 对比/消融/方差全部失去意义。
   同一份缓存还会被评测写脏，反过来喂给真实用户。

2. ``override_settings`` 直接 ``UPDATE ai_query_settings`` 再恢复。一次消融要跑
   几分钟，这期间**所有真实用户的问数都跑在消融配置下**（比如 recall 被关掉）。

这里钉住：评测期间缓存必须**既不读也不写**，配置覆盖必须**不落库、不外溢**。
"""

import asyncio

from sqlalchemy import text as _t


# ---------------------------------------------------------------------------
# 一、缓存旁路
# ---------------------------------------------------------------------------
def test_bypass_caches_disables_sql_cache():
    """评测上下文里 SQL 缓存既不命中也不写入。"""
    from app.plugin.module_ai.query.service import (
        _sql_cache_get,
        _sql_cache_set,
        bypass_caches,
    )

    _sql_cache_set("q_bypass_probe", "system", "SELECT 1")
    assert _sql_cache_get("q_bypass_probe", "system") == "SELECT 1"

    with bypass_caches():
        assert _sql_cache_get("q_bypass_probe", "system") is None, "评测不得命中缓存"
        _sql_cache_set("q_bypass_probe2", "system", "SELECT 2")
    assert _sql_cache_get("q_bypass_probe2", "system") is None, "评测不得写缓存"


def test_eval_ask_runs_inside_bypass_cache(monkeypatch):
    """``eval_runner._ask`` 必须包在旁路上下文里（否则上面那条旁路等于没接）。"""
    from app.plugin.module_ai.query import eval_runner
    from app.plugin.module_ai.query import service as svc

    seen: dict = {}

    async def fake_ask(question, auth, session_id=None, datasource=None,
                       redis=None, force_slow=False, **kw):
        seen["bypass"] = svc._BYPASS_CACHE.get()
        return {"sql": "", "rows": [], "is_error": False}

    monkeypatch.setattr(svc.AiQueryService, "ask", fake_ask)
    asyncio.run(eval_runner._ask("q", None, "system"))
    assert seen.get("bypass") is True


# ---------------------------------------------------------------------------
# 二、配置覆盖不落库、不外溢
# ---------------------------------------------------------------------------
KEY = "recall_enabled"


def test_override_settings_does_not_write_shared_table(test_client, db_run):
    """覆盖只在当前任务内生效，**不得改动** ai_query_settings 表。"""
    from app.core.database import async_db_session
    from app.plugin.module_ai.query.eval_runner import override_settings
    from app.plugin.module_ai.query.service import AiQueryService

    async def _read_db():
        async with async_db_session() as db:
            return (await db.execute(
                _t("SELECT value FROM ai_query_settings WHERE key=:k"), {"k": KEY})).scalar()

    async def _go():
        cfg_before = (await AiQueryService._cfg()).get(KEY)
        before = await _read_db()
        async with override_settings({KEY: "false"}):
            in_db = await _read_db()
            cfg = await AiQueryService._cfg()
            in_cfg = cfg.get(KEY)
        after = await _read_db()
        cfg_after = (await AiQueryService._cfg()).get(KEY)
        return before, in_db, in_cfg, after, cfg_before, cfg_after

    before, in_db, in_cfg, after, cfg_before, cfg_after = db_run(_go())
    assert str(in_cfg).lower() == "false", "覆盖没生效"
    assert in_db == before, "覆盖写了共享表（真实用户会被一起改掉）"
    assert after == before
    assert str(cfg_after) == str(cfg_before), "退出后配置没恢复"


def test_override_settings_does_not_leak_to_concurrent_task(test_client, db_run):
    """覆盖期间，**另一个任务**（等价于另一个正在跑的用户请求）不受影响。"""
    from app.plugin.module_ai.query.eval_runner import override_settings
    from app.plugin.module_ai.query.service import AiQueryService

    async def _peer():
        await asyncio.sleep(0.05)
        return (await AiQueryService._cfg()).get(KEY)

    async def _go():
        base = (await AiQueryService._cfg()).get(KEY)
        peer = asyncio.create_task(_peer())  # 覆盖之前创建 → 继承当时的上下文
        async with override_settings({KEY: "false"}):
            await asyncio.sleep(0.2)
            inside = (await AiQueryService._cfg()).get(KEY)
        peer_value = await peer
        return base, inside, peer_value

    base, inside, peer_value = db_run(_go())
    assert str(inside).lower() == "false", "覆盖没生效"
    assert str(peer_value) == str(base), f"配置外溢到并发任务：peer={peer_value} base={base}"
