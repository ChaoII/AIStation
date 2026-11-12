"""本体召回通道的回归：`ont_` 前缀与「更具体的别名优先」。

实测踩坑（2026-11-12）：`object_table_map()` 同时给出 `ont_x -> x` 和 `x -> x`，
旧实现用 `setdefault` 把 `ont_x` 固化成返回表名 → 与 schema 对不上，**整条本体通道的
分数被丢弃**（留出集里别名命中也不生效）。本用例锁住两个不变量。
"""
from __future__ import annotations

from app.plugin.module_ai.query.recall import recall_ontology


def test_prefers_plain_table_name_over_ont_prefix():
    objects = [
        {"code": "coal_batch", "name": "入厂煤批次", "aliases": ["入厂煤批次"], "properties": []},
    ]
    table_map = {"ont_FUEL_CMCS_INFACTORYBATCH": "coal_batch",
                 "FUEL_CMCS_INFACTORYBATCH": "coal_batch"}
    out = recall_ontology("入厂煤批次有多少条", objects, table_map)
    assert out == ["FUEL_CMCS_INFACTORYBATCH"]


def test_longer_alias_wins_within_tier():
    objects = [
        {"code": "a", "name": "煤场初始化主表", "aliases": ["期初库存"], "properties": []},
        {"code": "b", "name": "煤场初始化明细表", "aliases": ["期初库存", "期初库存明细"],
         "properties": []},
    ]
    table_map = {"FUEL_STG_STORAGEINITIALIZE": "a",
                 "FUEL_STG_STORAGEINITIALIZEDETAIL": "b"}
    out = recall_ontology("期初库存明细一共有多少条", objects, table_map)
    assert out[0] == "FUEL_STG_STORAGEINITIALIZEDETAIL"
    assert "FUEL_STG_STORAGEINITIALIZE" in out


def test_no_alias_no_hit():
    objects = [{"code": "a", "name": "煤质信息", "aliases": [], "properties": []}]
    assert recall_ontology("随便问一句", objects, {"DTXY_PMXX": "a"}) == []
