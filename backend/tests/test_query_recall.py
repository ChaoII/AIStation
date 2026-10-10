"""问数召回服务单测：RRF 融合、单元构建、四路通道、编排。

测试环境是 SQLite（无 pgvector），因此向量通道只验证「可降级」；
融合/关键词/本体/编排是这里的重点。
"""
import asyncio

import pytest


def _run(coro):
    return asyncio.run(coro)


# ===========================================================================
# Task 1: RRF 融合器
# ===========================================================================
def test_rrf_single_channel_preserves_order():
    from app.plugin.module_ai.query.recall import fuse_rrf

    out = fuse_rrf({"keyword": ["a", "b", "c"]})
    assert [t for t, _ in out] == ["a", "b", "c"]


def test_rrf_multi_channel_accumulates_not_duplicates():
    from app.plugin.module_ai.query.recall import fuse_rrf

    out = fuse_rrf(
        {"keyword": ["a", "b"], "ontology": ["b", "a"]},
        weights={"keyword": 1.0, "ontology": 1.0},
    )
    names = [t for t, _ in out]
    assert names == ["a", "b"]  # 无重复
    assert out[0][1] == pytest.approx(1 / 61 + 1 / 62)  # 两路累加


def test_rrf_ontology_weight_beats_keyword_at_equal_rank():
    from app.plugin.module_ai.query.recall import fuse_rrf

    out = fuse_rrf({"ontology": ["x"], "keyword": ["y"]})
    assert [t for t, _ in out] == ["x", "y"]  # ontology 权重 1.2 > keyword 0.8


def test_rrf_ignores_empty_and_unknown_channels():
    from app.plugin.module_ai.query.recall import fuse_rrf

    out = fuse_rrf({"keyword": ["a"], "vector": [], "nope": ["z"]})
    assert [t for t, _ in out] == ["a"]


def test_rrf_is_deterministic_on_ties():
    from app.plugin.module_ai.query.recall import DEFAULT_WEIGHTS, fuse_rrf

    a = fuse_rrf({"keyword": ["b", "a"]})
    b = fuse_rrf({"keyword": ["b", "a"]})
    assert a == b
    assert DEFAULT_WEIGHTS["ontology"] > DEFAULT_WEIGHTS["keyword"]


# ===========================================================================
# Task 2: 语义单元构建器
# ===========================================================================
def test_table_unit_text_carries_chinese_metadata():
    from app.plugin.module_ai.query.recall import build_table_unit

    u = build_table_unit(
        "FUEL_CB_COALBALANCE",
        {"alias": "燃煤采购结算主表", "domain": "燃煤", "description": "存煤款结算"},
        [{"column_name": "COALMONEY", "description": "煤款金额"}],
    )
    assert u["kind"] == "table" and u["ref"] == "FUEL_CB_COALBALANCE"
    assert u["meta"]["tables"] == ["FUEL_CB_COALBALANCE"]
    for token in ("燃煤采购结算主表", "燃煤", "存煤款结算", "COALMONEY", "煤款金额"):
        assert token in u["text"]


def test_object_unit_text_carries_aliases_synonyms_and_relations():
    from app.plugin.module_ai.query.recall import build_object_unit

    u = build_object_unit(
        {"code": "sales_order", "name": "销售订单", "table": "demo_sales",
         "aliases": ["订单", "销售单"], "synonyms": "销售额,成交额"},
        [{"code": "amount", "name": "销售额"}],
        [{"source": "demo_sales", "target": "demo_customer",
          "source_field": "customer_id", "target_field": "id", "card": "many_to_one"}],
    )
    assert u["kind"] == "object"
    assert u["meta"]["tables"] == ["demo_sales"]
    for token in ("销售订单", "订单", "销售单", "销售额", "demo_sales", "demo_customer"):
        assert token in u["text"]


def test_metric_and_term_units_are_minimal_but_complete():
    from app.plugin.module_ai.query.recall import build_metric_unit, build_term_unit

    m = build_metric_unit(
        {"key": "sales_amount", "name": "销售额", "sql_template": "SELECT 1", "unit": "元"}
    )
    t = build_term_unit({"term": "产量", "metric_key": "output_count", "field_path": "t.qty"})
    assert m["kind"] == "metric" and "销售额" in m["text"] and "元" in m["text"]
    assert t["kind"] == "term" and "产量" in t["text"] and "output_count" in t["text"]


def test_concept_unit_carries_synonyms_and_tables():
    from app.plugin.module_ai.query.recall import build_concept_unit

    u = build_concept_unit(
        {"name": "燃煤批次", "description": "一次入炉的煤", "synonyms": "批次,炉次",
         "domain": "燃煤", "tables": ["FUEL_BATCH"]}
    )
    assert u["kind"] == "concept" and u["ref"] == "燃煤批次"
    assert u["meta"]["tables"] == ["FUEL_BATCH"]
    for token in ("燃煤批次", "一次入炉的煤", "炉次", "FUEL_BATCH"):
        assert token in u["text"]


# ===========================================================================
# Task 4: 向量通道（无 pgvector 时降级）
# ===========================================================================
def test_vector_channel_degrades_without_pgvector():
    async def _run():
        from app.plugin.module_ai.query.service import AiQueryService as S

        # 测试库是 SQLite，没有 pgvector → 必须优雅降级为空列表，且不抛异常
        assert await S._recall_vector("各框架下的训练模型数量", 8) == []

    asyncio.run(_run())


# ===========================================================================
# Task 6: 编排 —— 并行四路 + RRF + 阈值 + 按分数 top_k
# ===========================================================================
def _patch_orchestration(monkeypatch, channels: dict, top_k: int = 12):
    """把编排依赖（四路通道 + 配置 + KG）打桩，使 ``_semantic_tables_uncached`` 不碰 DB。

    测试库是 SQLite：``_system_schema()`` 查 ``information_schema``（PG 专有）会失败，
    关键词/实体通道天然不可用。要测的是**编排契约**（并行融合、阈值、截断、兜底），
    所以把数据来源打桩，测试既稳定又能跑在 ``PYTEST_NO_APP=1`` 的快速模式。
    """
    from app.plugin.module_ai.query import service as S

    A = S.AiQueryService

    def _mk(name):
        async def _fn(cls, *a, **k):
            return list(channels.get(name) or [])
        return classmethod(_fn)

    for name in ("_recall_vector", "_recall_keyword", "_recall_ontology", "_recall_entity"):
        monkeypatch.setattr(A, name, _mk(name[8:]))

    async def _cfg(cls):
        return {}

    monkeypatch.setattr(A, "_cfg", classmethod(_cfg))
    monkeypatch.setattr(
        A, "_cfg_bool",
        classmethod(lambda cls, cfg, key, default=True:
                    False if key == "kg_enabled" else default),
    )
    monkeypatch.setattr(
        A, "_cfg_int",
        classmethod(lambda cls, cfg, key, default: top_k if key == "recall_top_k" else default),
    )
    monkeypatch.setattr(
        A, "_cfg_float", classmethod(lambda cls, cfg, key, default: default)
    )


def test_recall_takes_topk_by_score_not_alphabetical(monkeypatch):
    """决定性：按分数取 top_k，而不是 sorted() 的字典序。旧实现会给 aaa_early。"""
    _patch_orchestration(
        monkeypatch, {"keyword": ["zzz_late", "aaa_early"], "ontology": ["zzz_late"]}, top_k=1
    )

    async def _run():
        from app.plugin.module_ai.query.service import AiQueryService as A

        out = await A._semantic_tables_uncached("x", {}, [], [])
        assert out[0] == "zzz_late"

    asyncio.run(_run())


def test_recall_falls_back_to_core_tables_when_nothing_matches(monkeypatch):
    """完全无匹配 → 回退核心业务表，不能返回空（空集合会让 prompt 无表可用）。"""
    _patch_orchestration(monkeypatch, {})

    async def _run():
        from app.plugin.module_ai.query.recall import CORE_TABLES
        from app.plugin.module_ai.query.service import AiQueryService as A

        out = await A._semantic_tables_uncached("今天天气怎么样", {}, [], [])
        assert out == list(CORE_TABLES)

    asyncio.run(_run())


def test_recall_is_deterministic_across_calls(monkeypatch):
    _patch_orchestration(
        monkeypatch,
        {"keyword": ["video_cameras", "video_alarm_records"], "ontology": ["video_cameras"]},
    )

    async def _run():
        from app.plugin.module_ai.query.service import AiQueryService as A

        a = await A._semantic_tables_uncached("每个摄像头各产生多少条告警", {}, [], [])
        b = await A._semantic_tables_uncached("每个摄像头各产生多少条告警", {}, [], [])
        assert a == b and a

    asyncio.run(_run())


def test_recall_survives_empty_unit_table(monkeypatch):
    """单元表为空（向量通道无结果）时，仍须靠其余通道召回。"""
    _patch_orchestration(monkeypatch, {"vector": [], "keyword": ["video_cameras"]})

    async def _run():
        from app.plugin.module_ai.query.service import AiQueryService as A

        out = await A._semantic_tables_uncached("在线摄像头有多少", {}, [], [])
        assert "video_cameras" in out

    asyncio.run(_run())


# ===========================================================================
# Task 5: 关键词 / 本体强信号 / 实体 三路
# ===========================================================================
def test_ontology_channel_orders_alias_above_object_name():
    from app.plugin.module_ai.query.recall import recall_ontology

    objects = [
        {"code": "sales_order", "name": "销售订单", "aliases": ["订单"],
         "synonyms": "", "table": "demo_sales"},
        {"code": "camera", "name": "摄像头", "aliases": [], "synonyms": "",
         "table": "video_cameras"},
    ]
    table_map = {"demo_sales": "sales_order", "video_cameras": "camera"}
    # 「订单」是别名命中，「摄像头」是对象名命中 → 别名必须排在前面
    assert recall_ontology("订单和摄像头各多少", objects, table_map) == [
        "demo_sales", "video_cameras",
    ]
    # 只出现对象名时也能召回（权重低，但不丢）
    assert recall_ontology("摄像头有多少", objects, table_map) == ["video_cameras"]


def test_keyword_channel_ranks_chinese_comment_hit_first():
    from app.plugin.module_ai.query.recall import recall_keyword

    schema = {
        "FUEL_CB_COALBALANCE": ["COALMONEY(varchar)【煤款金额】"],
        "zzz_other": ["x(varchar)"],
    }
    out = recall_keyword("煤款金额是多少", schema, [], [])
    assert out and out[0] == "FUEL_CB_COALBALANCE"


def test_entity_channel_matches_noun():
    from app.plugin.module_ai.query.recall import recall_entity

    schema = {"video_cameras": [], "sys_user": []}
    assert recall_entity("摄像头有多少", {"摄像头": ["video_cameras"]}, schema) == [
        "video_cameras"
    ]


# ===========================================================================
# Task 3: 单元表 + 重建（幂等）
# ===========================================================================
def test_rebuild_is_idempotent_and_upserts():
    async def _run():
        from sqlalchemy import text

        from app.core.database import async_db_session
        from app.plugin.module_ai.query.service import AiQueryService as S

        await S._ensure_recall_units_table()
        first = await S.rebuild_recall_units()
        second = await S.rebuild_recall_units()
        assert first["units"] > 0
        assert second["units"] == first["units"]  # 幂等：不重复膨胀
        async with async_db_session() as db:
            n = (
                await db.execute(text("SELECT count(*) FROM ai_query_recall_units"))
            ).scalar()
        assert n == first["units"]

    asyncio.run(_run())
