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
