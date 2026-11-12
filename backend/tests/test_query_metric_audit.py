"""治理体检（可疑指标 / 抢答 / 悬空引用）的纯逻辑用例。

悬空引用的判定依赖「已知表集合」，所以用 monkeypatch 注入，不碰数据库。
"""
from __future__ import annotations

import asyncio

from app.plugin.module_ai.query import metric_audit as MA


def test_norm_table_strips_ont_prefix_and_case():
    assert MA._norm_table("ont_FUEL_X") == "FUEL_X"
    assert MA._norm_table("  fuel_x ") == "FUEL_X"
    assert MA._norm_table("") == ""
    assert MA._norm_table(None) == ""


def test_add_table_registers_both_forms():
    store: set[str] = set()
    MA._add_table(store, "ont_FUEL_X")
    assert store == {"ONT_FUEL_X", "FUEL_X"}
    MA._add_table(store, "")
    assert len(store) == 2


def test_dangling_flags_missing_metric_table_and_term_field(monkeypatch):
    async def fake_known(_ds: str) -> set[str]:
        return {"FUEL_X"}

    async def fake_ont(_ds: str) -> dict:
        return {}

    async def fake_terms(_ds: str) -> list[dict]:
        return [{"term": "灰分", "field_path": "FUEL_MISSING.AD"}]

    monkeypatch.setattr(MA, "_known_tables", fake_known)
    monkeypatch.setattr(MA, "_ont_objects", fake_ont)
    monkeypatch.setattr(MA, "_terms", fake_terms)

    out = asyncio.run(MA._dangling(
        "ds:6",
        [{"key": "k1", "name": "缺表指标", "sql_template": "SELECT 1 FROM FUEL_MISSING"}],
    ))
    kinds = {d["kind"] for d in out}
    assert "metric_table" in kinds
    assert "term_field" in kinds


def test_dangling_accepts_ont_prefixed_and_bound_object_table(monkeypatch):
    """`ont_` 前缀与绑定型指标（走对象支撑表）都不算悬空。"""
    async def fake_known(_ds: str) -> set[str]:
        return {"FUEL_X", "FUEL_BOUND"}

    async def fake_ont(_ds: str) -> dict:
        return {"fuel_x": {"table": "FUEL_BOUND", "datasource": "ds:6"}}

    async def fake_terms(_ds: str) -> list[dict]:
        return []

    monkeypatch.setattr(MA, "_known_tables", fake_known)
    monkeypatch.setattr(MA, "_ont_objects", fake_ont)
    monkeypatch.setattr(MA, "_terms", fake_terms)

    out = asyncio.run(MA._dangling("ds:6", [
        {"key": "k1", "name": "绑定型", "object_code": "fuel_x", "sql_template": "SELECT 1"},
        {"key": "k2", "name": "影子表", "sql_template": "SELECT 1 FROM ont_FUEL_X"},
    ]))
    assert out == []
