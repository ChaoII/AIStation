"""数据治理能力 → Agent 工具：派发与参数路由。"""
import asyncio

from app.plugin.module_ai.query import agent_tools as G
from app.plugin.module_ai.query.service import AiQueryService


def test_governance_dispatch(monkeypatch):
    calls: dict = {}

    async def _overview():
        calls["overview"] = True
        return {"domains": 2}

    async def _dq_run(table):
        calls["dq"] = table
        return {"table": table, "score": 88}

    async def _dq_overview():
        return {"avg": 80}

    async def _lineage(table):
        return {"table": table, "nodes": 3}

    async def _impact(table):
        return {"table": table, "affected": 5}

    monkeypatch.setattr(AiQueryService, "governance_overview", staticmethod(_overview))
    monkeypatch.setattr(AiQueryService, "dq_run", staticmethod(_dq_run))
    monkeypatch.setattr(AiQueryService, "dq_overview", staticmethod(_dq_overview))
    monkeypatch.setattr(AiQueryService, "lineage", staticmethod(_lineage))
    monkeypatch.setattr(AiQueryService, "impact_analysis", staticmethod(_impact))

    assert asyncio.run(G.run_governance_tool("governance_overview", {})) == {"domains": 2}
    assert asyncio.run(G.run_governance_tool("data_quality", {"table_name": "ai_models"}))["score"] == 88
    assert calls["dq"] == "ai_models"
    # 无表名 → DQ 概览
    assert asyncio.run(G.run_governance_tool("data_quality", {})) == {"avg": 80}
    # 血缘 full / impact
    assert asyncio.run(G.run_governance_tool("data_lineage", {"table_name": "t"}))["nodes"] == 3
    assert asyncio.run(G.run_governance_tool("data_lineage", {"table_name": "t", "mode": "impact"}))["affected"] == 5
    # 缺表名 → 错误
    assert "error" in asyncio.run(G.run_governance_tool("data_lineage", {}))


def test_governance_tool_names():
    assert G.GOVERNANCE_TOOL_NAMES == {
        "governance_overview",
        "data_quality",
        "data_quality_alert",
        "list_data_domains",
        "data_lineage",
        "list_access_rules",
    }
