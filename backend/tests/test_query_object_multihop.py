"""P3 多跳 traverse + 关联集聚合测试。

覆盖：
- 执行层纯逻辑（算子匹配 / 目标过滤 / 去重 / 聚合）。
- ``validate_ir`` 的多跳截断、集合级 traverse（无需 object_key）、派生属性。
- ``_execute_traverse``（打桩本体实例层）的多跳、关联集聚合、失败降级。

纯逻辑部分可 ``PYTEST_NO_APP=1`` 快测；``_execute_traverse`` 用 monkeypatch 注入
本体实例层，避免依赖真实的本体库 fixtures。
"""
from __future__ import annotations

import pytest

from app.plugin.module_ai.query.object_exec import (
    _aggregate_rows,
    _apply_filters,
    _dedupe_items,
    _execute_traverse,
    _match_op,
)
from app.plugin.module_ai.query.object_query import ObjectQueryIR, validate_ir

# ---------------------------------------------------------------------------
# 纯逻辑：算子 / 过滤 / 去重 / 聚合
# ---------------------------------------------------------------------------


def test_match_op():
    assert _match_op(5, "eq", "5")
    assert _match_op(5, "ne", 6)
    assert _match_op(5, "gt", 3)
    assert _match_op(5, "gte", 5)
    assert _match_op(5, "lt", 8)
    assert _match_op(5, "lte", 5)
    assert _match_op(5, "in", [3, 5, 9])
    assert _match_op("abcd", "contains", "bc")
    assert _match_op(None, "is_empty", None)
    assert _match_op("", "is_empty", None)
    assert _match_op("x", "not_empty", None)
    assert not _match_op(5, "gt", 8)
    assert not _match_op(None, "eq", 5)
    assert not _match_op("abc", "contains", "zzz")


def test_apply_filters():
    items = [
        {"props": {"severity": "HIGH", "region": "华东"}},
        {"props": {"severity": "LOW", "region": "华东"}},
        {"props": {"severity": "HIGH", "region": "华南"}},
    ]
    out = _apply_filters(items, [{"field": "severity", "op": "eq", "value": "HIGH"}])
    assert len(out) == 2
    out2 = _apply_filters(
        items,
        [{"field": "severity", "op": "eq", "value": "HIGH"},
         {"field": "region", "op": "eq", "value": "华东"}])
    assert len(out2) == 1 and out2[0]["props"]["region"] == "华东"


def test_dedupe_items():
    items = [
        {"object_code": "a", "key": "1"},
        {"object_code": "a", "key": "1"},
        {"object_code": "a", "key": "2"},
        {"object_code": "b", "key": "1"},
    ]
    assert len(_dedupe_items(items)) == 3


def test_aggregate_rows_count():
    items = [
        {"props": {"region": "华东"}},
        {"props": {"region": "华东"}},
        {"props": {"region": "华南"}},
    ]
    rows = _aggregate_rows(items, "region", [{"fn": "count"}])
    assert dict(rows) == {"华东": 2, "华南": 1}


def test_aggregate_rows_sum_avg_min_max():
    items = [{"props": {"amt": 10}}, {"props": {"amt": 20}}, {"props": {"amt": 30}}]
    assert _aggregate_rows(items, "", [{"fn": "sum", "field": "amt"}]) == [["合计", 60.0]]
    assert _aggregate_rows(items, "", [{"fn": "avg", "field": "amt"}]) == [["合计", 20.0]]
    assert _aggregate_rows(items, "", [{"fn": "min", "field": "amt"}]) == [["合计", 10.0]]
    assert _aggregate_rows(items, "", [{"fn": "max", "field": "amt"}]) == [["合计", 30.0]]


# ---------------------------------------------------------------------------
# validate_ir：多跳 / 集合级 / 派生属性
# ---------------------------------------------------------------------------

_ALLOWED = {
    "cameras": {
        "name": "摄像机表",
        "fields": {"id": {"name": "ID", "type": "string"},
                   "status": {"name": "状态", "type": "string"}},
        "links": {"cam_has_alarms": {"id": 3, "target": "alarms"},
                  "cam_has_people": {"id": 5, "target": "people"}},
    },
}


def test_validate_ir_multihop_truncates_not_voids():
    ir = ObjectQueryIR(
        object="cameras",
        filters=[{"field": "status", "op": "eq", "value": "ONLINE"}],
        traverse=[
            {"link": "cam_has_alarms", "direction": "auto", "filters": []},
            {"link": "cam_has_people", "direction": "auto", "filters": []},
            {"link": "cam_has_alarms", "direction": "auto", "filters": []},
        ],
    )
    out, reasons = validate_ir(ir, _ALLOWED, max_traverse_depth=2)
    # 不是整条作废，而是截断到上限
    assert out is not None
    assert len(out.traverse) == 2
    assert any("超" in r for r in reasons)


def test_validate_ir_default_depth_one_truncates():
    ir = ObjectQueryIR(object="cameras", traverse=[
        {"link": "cam_has_alarms", "direction": "auto", "filters": []},
        {"link": "cam_has_people", "direction": "auto", "filters": []},
    ])
    out, reasons = validate_ir(ir, _ALLOWED)   # 默认 max_traverse_depth=1
    assert out is not None
    assert len(out.traverse) == 1


def test_validate_ir_set_level_traverse_no_key_allowed():
    ir = ObjectQueryIR(object="cameras", filters=[{"field": "status", "op": "eq", "value": "ONLINE"}],
                       traverse=[{"link": "cam_has_alarms", "direction": "auto", "filters": []}])
    out, _ = validate_ir(ir, _ALLOWED, max_traverse_depth=2)
    assert out is not None
    assert len(out.traverse) == 1


def test_validate_ir_sanitizes_traverse_filter_op():
    ir = ObjectQueryIR(object="cameras",
                       traverse=[{"link": "cam_has_alarms", "direction": "auto",
                                  "filters": [{"field": "severity", "op": "foo", "value": "HIGH"}]}])
    out, reasons = validate_ir(ir, _ALLOWED, max_traverse_depth=2)
    assert out is not None
    assert out.traverse[0]["filters"] == []


def test_validate_ir_derived_property_single():
    ir = ObjectQueryIR(object="cameras", object_key="1", derived_property="alert_count")
    out, _ = validate_ir(ir, _ALLOWED)
    assert out is not None
    assert out.derived_property == "alert_count"


def test_validate_ir_derived_property_truncate():
    ir = ObjectQueryIR(object="cameras", object_key="1", derived_property="a,b")
    out, reasons = validate_ir(ir, _ALLOWED)
    assert out is not None
    assert out.derived_property == "a"
    assert any("单个" in r for r in reasons)


# ---------------------------------------------------------------------------
# _execute_traverse：打桩本体实例层
# ---------------------------------------------------------------------------


def _patch_ont(monkeypatch, pivots=None, search=None):
    import asyncio

    import app.plugin.module_ai.ontology.service as ont

    async def fake_meta(code):
        return {"materialized": True, "code": code}

    async def fake_search(code, **kw):
        return {"ok": True, "items": [{"key": "1", "object_code": "cameras", "props": {"id": 1}}]}

    async def fake_links(code):
        return [{"id": 3, "name": "cam_has_alarms"}]

    monkeypatch.setattr(ont, "_instance_meta", fake_meta)
    monkeypatch.setattr(ont, "instance_search", search or fake_search)
    monkeypatch.setattr(ont, "instance_pivot", pivots or fake_search)
    monkeypatch.setattr(ont, "list_links", fake_links)
    return asyncio


def test_execute_traverse_aggregate(monkeypatch):
    async def pivot(code, key, link_id, **kw):
        return {"ok": True, "items": [
            {"key": "10", "object_code": "alarms", "props": {"severity": "HIGH"}},
            {"key": "11", "object_code": "alarms", "props": {"severity": "HIGH"}},
        ], "other_object": "alarms"}

    asyncio = _patch_ont(monkeypatch, pivots=pivot)
    ir = ObjectQueryIR(
        object="cameras", filters=None, limit=100,
        traverse=[{"link": "cam_has_alarms", "direction": "auto", "filters": []}],
        group_by=[{"field": "severity", "alias": "级别"}],
        aggregations=[{"fn": "count", "field": "", "alias": "数量"}],
    )
    res = asyncio.run(_execute_traverse(ir, principal=None))
    assert res["ok"]
    assert res["shape"] == "traverse-agg"
    assert res["columns"] == ["级别", "数量"]
    assert dict(zip(res["columns"], res["rows"][0])) == {"级别": "HIGH", "数量": 2}


def test_execute_traverse_multihop(monkeypatch):
    async def pivot(code, key, link_id, **kw):
        if code == "cameras":
            return {"ok": True, "items": [
                {"key": "10", "object_code": "alarms", "props": {"severity": "HIGH"}},
            ], "other_object": "alarms"}
        return {"ok": True, "items": [], "other_object": "people"}

    asyncio = _patch_ont(monkeypatch, pivots=pivot)
    ir = ObjectQueryIR(
        object="cameras", limit=100,
        traverse=[{"link": "cam_has_alarms", "direction": "auto", "filters": []},
                  {"link": "cam_has_alarms", "direction": "auto", "filters": []}],
    )
    res = asyncio.run(_execute_traverse(ir, principal=None))
    assert res["ok"]
    # 第二跳 pivot 返回空 → 集合为空，返回空结果但不失败
    assert res["rows"] == []
    assert res["shape"] == "traverse"


def test_execute_traverse_link_missing_degrades(monkeypatch):
    async def pivot(code, key, link_id, **kw):
        return {"ok": True, "items": [], "other_object": "alarms"}

    asyncio = _patch_ont(monkeypatch, pivots=pivot)
    ir = ObjectQueryIR(object="cameras", limit=100,
                       traverse=[{"link": "no_such_link", "direction": "auto", "filters": []}])
    res = asyncio.run(_execute_traverse(ir, principal=None))
    assert res["ok"] is False
