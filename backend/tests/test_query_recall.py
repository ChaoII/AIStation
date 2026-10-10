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
