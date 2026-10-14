"""对象查询（语义执行层）端到端：三分支路由 + **失败必降级**契约。

打桩 LLM 与实例层，不真的调模型、不依赖真实本体数据；
需要应用上下文（会话/消息表），故用 ``test_client`` 夹具 —— ``PYTEST_NO_APP=1`` 时自动 skip。

设计依据：docs/superpowers/specs/2026-10-14-semantic-query-layer-design.md
"""
from types import SimpleNamespace

import pytest

from app.plugin.module_ai.query.service import AiQueryService

_ALLOWED = {
    "video_cameras": {
        "name": "摄像机表",
        "fields": {"status": {"name": "状态", "type": "enum", "options": ["ONLINE"]}},
        "links": {},
    }
}
_IR_OK = (
    '{"object":"video_cameras","group_by":[{"field":"status","alias":"状态"}],'
    '"aggregations":[{"fn":"count","field":"","alias":"数量"}]}'
)


def _auth():
    return SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))


@pytest.fixture(autouse=True)
def _need_app(test_client):
    """所有用例都需要应用上下文（无应用时自动 skip，见 conftest）。"""
    return test_client


def _stub(monkeypatch, *, allowed=_ALLOWED, ir_text=_IR_OK, exec_ok=True):
    async def _allowed(question, auth, max_objects=8, datasource="system",
                       prefer_object=None):
        return dict(allowed)

    async def _ir_llm(prompt, runtime):
        return ir_text

    async def _exec(ir, principal=None, metrics=None):
        if not exec_ok:
            return {"ok": False, "error": "实例层炸了"}
        return {"ok": True, "columns": ["状态", "数量"], "rows": [["ONLINE", 55]],
                "shape": "aggregate", "note": ""}

    async def _recall(question, datasource=None):
        return {"tables": ["video_cameras"], "fields": {}}

    monkeypatch.setattr(AiQueryService, "_allowed_objects_for_query", _allowed)
    monkeypatch.setattr(AiQueryService, "_ir_llm", _ir_llm)
    monkeypatch.setattr(AiQueryService, "_recall_grounding", _recall)
    # `_object_query_path` 在函数内 `from .object_exec import execute_ir`，故补丁模块属性即可
    monkeypatch.setattr(
        "app.plugin.module_ai.query.object_exec.execute_ir", _exec)


# ---------------------------------------------------------------------------
# _object_query_path：成功与各降级分支
# ---------------------------------------------------------------------------
def test_object_path_returns_object_answer(monkeypatch):
    import asyncio

    _stub(monkeypatch)

    async def _go():
        return await AiQueryService._object_query_path(
            "统计摄像机的状态分布", 1, "system", _auth())

    ans = asyncio.run(_go())
    assert ans is not None
    assert ans["path"] == "object"
    assert ans["confidence"] == 0.95                      # 高于 NL2SQL 的 0.85
    assert ans["evidence"]["source"] == "本体对象查询"
    assert ans["sql"] == ""                               # 对象查询不生成 SQL
    assert ans["ontology_used"] == ["video_cameras"]
    assert ans["columns"] == ["状态", "数量"]
    assert ans["rows"] == [["ONLINE", 55]]
    assert ans["ir"]["object"] == "video_cameras"         # IR 一并返回（前端可展示）


def test_object_path_degrades_without_allowed_objects(monkeypatch):
    import asyncio

    _stub(monkeypatch, allowed={})

    async def _go():
        return await AiQueryService._object_query_path("随便问", 1, "system", _auth())

    assert asyncio.run(_go()) is None                     # 无可用对象 → 降级


def test_object_path_degrades_on_unparsable_ir(monkeypatch):
    import asyncio

    _stub(monkeypatch, ir_text="这是一段没有 JSON 的话")

    async def _go():
        return await AiQueryService._object_query_path("统计摄像机状态", 1, "system", _auth())

    assert asyncio.run(_go()) is None


def test_object_path_degrades_on_out_of_scope_object(monkeypatch):
    """IR 引用了清单外的对象 → 整条作废（scope 收敛的关键保证）。"""
    import asyncio

    _stub(monkeypatch,
          ir_text='{"object":"secret_table","filters":[{"field":"id","op":"eq","value":1}]}')

    async def _go():
        return await AiQueryService._object_query_path("查机密表", 1, "system", _auth())

    assert asyncio.run(_go()) is None


def test_object_path_degrades_when_execute_fails(monkeypatch):
    import asyncio

    _stub(monkeypatch, exec_ok=False)

    async def _go():
        return await AiQueryService._object_query_path("统计摄像机状态", 1, "system", _auth())

    assert asyncio.run(_go()) is None


def test_object_path_attempts_custom_datasource(monkeypatch):
    """S2：对象查询**放开**自定义数据源——按对象归属过滤词表，不再无条件降级。"""
    import asyncio

    called = {"n": 0}

    async def _allowed(question, auth, max_objects=8, datasource="system",
                       prefer_object=None):
        called["n"] += 1
        called["datasource"] = datasource
        return {}          # 无可用对象 → 仍降级，但**已构建过词表**

    monkeypatch.setattr(AiQueryService, "_allowed_objects_for_query", _allowed)

    async def _go():
        return await AiQueryService._object_query_path("统计摄像机状态", 1, "ds:4", _auth())

    assert asyncio.run(_go()) is None
    assert called["n"] == 1                               # 词表已构建（不再早退）
    assert called.get("datasource") == "ds:4"


# ---------------------------------------------------------------------------
# ask()：三分支路由
# ---------------------------------------------------------------------------
def _patch_ask_plumbing(monkeypatch):
    """关掉指标快路径与澄清检测，让 ask() 走到我们要测的分支。"""
    def _no_metric(question, metrics, terms):   # ⚠️ `_match_metric` 是**同步**函数
        return None

    def _no_clarify(question, schema_map):
        return None

    monkeypatch.setattr("app.plugin.module_ai.query.service._match_metric", _no_metric)
    monkeypatch.setattr("app.plugin.module_ai.query.clarify.detect_clarify", _no_clarify)


def test_ask_routes_to_object_when_enabled(monkeypatch):
    import asyncio

    _patch_ask_plumbing(monkeypatch)
    sentinel = {"path": "object", "sentinel": True}
    hit = {"object": 0, "slow": 0}

    async def _cfg():
        return {"object_query_enabled": "true"}

    async def _obj_path(question, session_id, datasource, auth, **kw):
        hit["object"] += 1
        return sentinel

    async def _slow(question, session_id, datasource, auth):
        hit["slow"] += 1
        return {"path": "slow"}

    monkeypatch.setattr(AiQueryService, "_cfg", _cfg)
    monkeypatch.setattr(AiQueryService, "_object_query_path", _obj_path)
    monkeypatch.setattr(AiQueryService, "_slow_path", _slow)

    ans = asyncio.run(AiQueryService.ask("统计摄像机的状态分布", _auth(), None, "system"))
    assert ans is sentinel
    assert hit == {"object": 1, "slow": 0}                # 命中对象查询，未走慢路径


def test_ask_falls_back_to_slow_when_disabled(monkeypatch):
    import asyncio

    _patch_ask_plumbing(monkeypatch)
    hit = {"object": 0, "slow": 0}

    async def _cfg():
        return {"object_query_enabled": "false"}          # 默认关

    async def _obj_path(question, session_id, datasource, auth, **kw):
        hit["object"] += 1
        return {"path": "object"}

    async def _slow(question, session_id, datasource, auth):
        hit["slow"] += 1
        return {"path": "slow"}

    monkeypatch.setattr(AiQueryService, "_cfg", _cfg)
    monkeypatch.setattr(AiQueryService, "_object_query_path", _obj_path)
    monkeypatch.setattr(AiQueryService, "_slow_path", _slow)

    ans = asyncio.run(AiQueryService.ask("统计摄像机的状态分布", _auth(), None, "system"))
    assert ans == {"path": "slow"}
    assert hit == {"object": 0, "slow": 1}                # 开关关 → 完全不进入对象查询


def test_ask_falls_back_to_slow_when_object_path_returns_none(monkeypatch):
    """对象查询返回 None（内部已降级）→ ask() 必须继续走慢路径，不能中断。"""
    import asyncio

    _patch_ask_plumbing(monkeypatch)
    hit = {"slow": 0}

    async def _cfg():
        return {"object_query_enabled": "true"}

    async def _obj_path(question, session_id, datasource, auth, **kw):
        return None

    async def _slow(question, session_id, datasource, auth):
        hit["slow"] += 1
        return {"path": "slow"}

    monkeypatch.setattr(AiQueryService, "_cfg", _cfg)
    monkeypatch.setattr(AiQueryService, "_object_query_path", _obj_path)
    monkeypatch.setattr(AiQueryService, "_slow_path", _slow)

    ans = asyncio.run(AiQueryService.ask("统计摄像机的状态分布", _auth(), None, "system"))
    assert ans == {"path": "slow"}
    assert hit["slow"] == 1


def test_ask_survives_object_path_exception(monkeypatch):
    """对象查询**抛异常**也不能让整题崩——必须降级。"""
    import asyncio

    _patch_ask_plumbing(monkeypatch)
    hit = {"slow": 0}

    async def _cfg():
        return {"object_query_enabled": "true"}

    async def _obj_path(question, session_id, datasource, auth, **kw):
        raise RuntimeError("意外炸了")

    async def _slow(question, session_id, datasource, auth):
        hit["slow"] += 1
        return {"path": "slow"}

    monkeypatch.setattr(AiQueryService, "_cfg", _cfg)
    monkeypatch.setattr(AiQueryService, "_object_query_path", _obj_path)
    monkeypatch.setattr(AiQueryService, "_slow_path", _slow)

    ans = asyncio.run(AiQueryService.ask("统计摄像机的状态分布", _auth(), None, "system"))
    assert ans == {"path": "slow"}
    assert hit["slow"] == 1


# ---------------------------------------------------------------------------
# 当前对象上下文（P1 / G3）：确定性注入 + 不阻断
# ---------------------------------------------------------------------------
def test_object_context_empty_without_code():
    import asyncio

    assert asyncio.run(AiQueryService._object_context_block(None, None, _auth())) == ""
    assert asyncio.run(AiQueryService._object_context_block("", "1", _auth())) == ""


def test_object_context_degrades_for_unknown_object():
    """对象不存在 → 空串（**不抛异常、不阻断**）。"""
    import asyncio

    out = asyncio.run(
        AiQueryService._object_context_block("no_such_object_xyz", "1", _auth()))
    assert out == ""


def test_build_schema_context_prepends_current_object(monkeypatch):
    """上下文块必须出现在 schema 上下文**最前面**（确定性注入，不是让模型自己找）。

    这里把 schema/本体/示例这些重活全部打桩：本用例只验证「注入」这一件事，
    它们依赖 Postgres 的 ``information_schema``，在 SQLite 测试库上跑不通。
    """
    import asyncio

    from app.plugin.module_ai.query import service as S

    async def _s(*_a, **_k):
        return ""

    async def _l(*_a, **_k):
        return []

    async def _d(*_a, **_k):
        return {}

    monkeypatch.setattr(S.AiQueryService, "_concept_context", _s)
    monkeypatch.setattr(S.AiQueryService, "_system_schema", _d)
    monkeypatch.setattr(S.AiQueryService, "_asset_tmeta", _d)
    monkeypatch.setattr(S.AiQueryService, "_semantic_tables", _l)
    monkeypatch.setattr(S.AiQueryService, "_ont_ctx_block", _s)
    monkeypatch.setattr(S.AiQueryService, "_dynamic_fewshots", _l)
    monkeypatch.setattr(S.AiQueryService, "_query_conventions", lambda: "")

    token = S._OBJECT_CTX.set("【当前对象】摄像机表 #1：status=ONLINE")
    try:
        async def _go():
            return await S.AiQueryService._build_schema_context("随便问", "system", [], [])

        ctx = asyncio.run(_go())
    finally:
        S._OBJECT_CTX.reset(token)
    assert ctx.startswith("【当前对象】"), ctx[:60]
    assert "摄像机表 #1" in ctx


def test_ask_passes_object_context_into_query_path(monkeypatch):
    """ask() 必须把 object_code/object_key 传到对象查询路径。"""
    import asyncio

    _patch_ask_plumbing(monkeypatch)
    seen = {}

    async def _cfg():
        return {"object_query_enabled": "true"}

    async def _obj_path(question, session_id, datasource, auth, **kw):
        seen.update(kw)
        return {"path": "object"}

    async def _slow(question, session_id, datasource, auth):
        return {"path": "slow"}

    monkeypatch.setattr(AiQueryService, "_cfg", _cfg)
    monkeypatch.setattr(AiQueryService, "_object_query_path", _obj_path)
    monkeypatch.setattr(AiQueryService, "_slow_path", _slow)

    asyncio.run(AiQueryService.ask("它现在什么状态", _auth(), None, "system",
                                   object_code="video_cameras", object_key="1"))
    assert seen.get("object_code") == "video_cameras"
    assert seen.get("object_key") == "1"


# ---------------------------------------------------------------------------
# 流式对象查询（P1 / T4）
# ---------------------------------------------------------------------------
def test_ask_stream_yields_ir_event(monkeypatch):
    """流式命中对象查询时先发 ``ir`` 事件，再发 ``result`` / ``done``（不再走 NL2SQL 流）。"""
    import asyncio

    async def _cfg():
        return {"object_query_enabled": "true"}

    async def _obj_path(question, session_id, datasource, auth, **kw):
        return {"path": "object", "ir": {"object": "video_cameras"},
                "object_query": {"shape": "aggregate"}, "confidence": 0.95,
                "columns": ["状态"], "rows": [["ONLINE"]], "summary": "s",
                "ontology_used": ["video_cameras"]}

    monkeypatch.setattr(AiQueryService, "_cfg", _cfg)
    monkeypatch.setattr(AiQueryService, "_object_query_path", _obj_path)

    async def _go():
        return [ev async for ev in
                AiQueryService.ask_stream("统计摄像机状态", _auth(), None, "system")]

    evs = asyncio.run(_go())
    types = [e.get("type") for e in evs]
    assert types[:2] == ["meta", "ir"], types
    assert "result" in types and types[-1] == "done"
    assert evs[-1].get("path") == "object"


# ---------------------------------------------------------------------------
# 热度驱动自动建索引（P1 / G4）
# ---------------------------------------------------------------------------
def test_auto_index_disabled_records_nothing(monkeypatch):
    import asyncio

    from app.plugin.module_ai.query import service as S

    called: list[str] = []

    async def _ai(code):
        called.append(code)

    monkeypatch.setattr(S.AiQueryService, "_auto_index", _ai)
    S._OQ_HEAT.clear()
    S._OQ_INDEXED.clear()

    async def _go():
        await S.AiQueryService._maybe_auto_index("tbl", {"object_query_auto_index_enabled": "false"})
        await asyncio.sleep(0)

    asyncio.run(_go())
    assert called == []
    assert S._OQ_HEAT.get("tbl") is None      # 开关关 → 连热度都不记（不产生副作用）


def test_auto_index_triggers_once_after_threshold(monkeypatch):
    import asyncio

    from app.plugin.module_ai.query import service as S

    called: list[str] = []

    async def _ai(code):
        called.append(code)

    monkeypatch.setattr(S.AiQueryService, "_auto_index", _ai)
    S._OQ_HEAT.clear()
    S._OQ_INDEXED.clear()
    cfg = {"object_query_auto_index_enabled": "true", "object_query_auto_index_after": "2"}

    async def _go():
        await S.AiQueryService._maybe_auto_index("tbl", cfg)   # 第 1 次：不够阈值
        await asyncio.sleep(0)
        await S.AiQueryService._maybe_auto_index("tbl", cfg)   # 第 2 次：触发
        await asyncio.sleep(0)
        await S.AiQueryService._maybe_auto_index("tbl", cfg)   # 第 3 次：不重复建
        await asyncio.sleep(0)

    asyncio.run(_go())
    assert called == ["tbl"]


def test_auto_index_failure_allows_retry(monkeypatch):
    """建索引失败要**回滚占位**，否则该对象永远等不到重试。"""
    import asyncio

    from app.plugin.module_ai.ontology import indexing as idx
    from app.plugin.module_ai.query import service as S

    async def _boom(*_a, **_k):
        raise RuntimeError("DDL 失败")

    monkeypatch.setattr(idx, "apply_suggestions", _boom)
    S._OQ_INDEXED.clear()
    S._OQ_INDEXED.add("tbl")

    asyncio.run(S.AiQueryService._auto_index("tbl"))
    assert "tbl" not in S._OQ_INDEXED
