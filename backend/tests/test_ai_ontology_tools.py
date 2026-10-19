"""本体能力 → Agent 工具：表达式求值、函数/动作派发、能力清单。"""
import asyncio

from app.plugin.module_ai.ontology import agent_tools as T
from app.plugin.module_ai.ontology import service as ont


def test_safe_eval():
    assert T._safe_eval("a * b - c", {"a": 2, "b": 3, "c": 1}) == 5
    assert T._safe_eval("price > 10", {"price": 12}) is True
    assert T._safe_eval("x >= 1 and y <= 2", {"x": 1, "y": 2}) is True


def test_run_ontology_function(monkeypatch):
    async def _funcs(_obj=None):
        return [{"code": "gross_margin", "name": "毛利率", "expr": "(rev - cost) / rev", "description": ""}]

    monkeypatch.setattr(ont, "list_functions", _funcs)
    r = asyncio.run(
        T.run_ontology_tool("run_ontology_function", {"code": "gross_margin", "args": {"rev": 100, "cost": 60}})
    )
    assert r["result"] == 0.4
    assert r["code"] == "gross_margin"


def test_propose_ontology_action(monkeypatch):
    async def _acts(_obj=None):
        return [{"code": "close_order", "name": "关单", "approval": True, "target_table": "ont_orders", "method": "update"}]

    monkeypatch.setattr(ont, "list_actions", _acts)
    r = asyncio.run(T.run_ontology_tool("propose_ontology_action", {"code": "close_order", "args": {"id": 1}}))
    act = r["__action__"]
    assert act["type"] == "confirm"
    assert act["api"] == "ontologyAction"
    assert act["payload"]["code"] == "close_order"


def test_build_selected_ontology_tools(monkeypatch):
    async def _funcs(_obj=None):
        return [{"code": "gm", "name": "毛利率", "expr": "(rev - cost) / rev", "description": ""}]

    async def _acts(_obj=None):
        return [
            {
                "code": "close",
                "name": "关单",
                "input_schema": [{"name": "id", "type": "integer"}],
                "target_table": "ont_orders",
                "method": "update",
                "approval": True,
            }
        ]

    monkeypatch.setattr(ont, "list_functions", _funcs)
    monkeypatch.setattr(ont, "list_actions", _acts)
    schemas, names = asyncio.run(T.build_selected_ontology_tools(["gm", "close", "missing"]))
    assert "ont_fn__gm" in names and "ont_action__close" in names
    assert "ont_fn__missing" not in names
    assert len(schemas) == 2
    r = asyncio.run(T.run_selected_ontology_tool("ont_fn__gm", {"rev": 100, "cost": 60}))
    assert r["result"] == 0.4


# test_cap_meta 已删除（2026-10-19）：本体能力登记特性整体下线，_cap_meta 随之移除。
# 智能体的能力字段 ai_agents.capabilities（函数/动作 code 列表）是另一回事，未受影响。


def test_list_ontology(monkeypatch):
    async def _objs():
        return [{"code": "orders", "name": "订单"}]

    async def _funcs(_obj=None):
        return [{"code": "gm", "name": "毛利率", "expr": "rev-cost", "description": ""}]

    async def _acts(_obj=None):
        return [{"code": "close", "name": "关单", "approval": True, "description": ""}]

    monkeypatch.setattr(ont, "list_objects", _objs)
    monkeypatch.setattr(ont, "list_functions", _funcs)
    monkeypatch.setattr(ont, "list_actions", _acts)
    r = asyncio.run(T.run_ontology_tool("list_ontology", {}))
    assert r["objects"][0]["object"] == "orders"
    assert r["objects"][0]["functions"][0]["code"] == "gm"
    assert r["objects"][0]["actions"][0]["code"] == "close"
    cat = asyncio.run(T.ontology_catalog_text())
    assert "可用本体能力" in cat and "orders" in cat
