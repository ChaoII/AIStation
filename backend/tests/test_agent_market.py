"""Agent 市场模板测试。"""
import asyncio
from types import SimpleNamespace as SN

from app.plugin.module_ai.agent.service import AiAgentService


class TestAgentMarket:
    def test_templates_nonempty(self):
        ts = asyncio.run(AiAgentService.agent_templates())
        assert ts and any(t["key"] == "query_assistant" for t in ts)
        assert any(t["query_enabled"] for t in ts)

    def test_create_from_template(self, test_client):
        auth = SN(user=SN(id=1))
        a = asyncio.run(AiAgentService.create_from_template("query_assistant", "", auth))
        assert a["agent_name"] == "问数助手"
        assert a["query_enabled"] is True

    def test_create_unknown_template(self, test_client):
        auth = SN(user=SN(id=1))
        import pytest
        with pytest.raises(ValueError):
            asyncio.run(AiAgentService.create_from_template("nope", "", auth))

    def test_agent_dashboard_shape(self):
        d = asyncio.run(AiAgentService.agent_dashboard())
        assert "agents" in d and "total_agents" in d and "total_runs" in d
        assert isinstance(d["agents"], list)
        if d["agents"]:
            a = d["agents"][0]
            assert "runs" in a and "error_rate" in a and "tools" in a and "skills" in a
