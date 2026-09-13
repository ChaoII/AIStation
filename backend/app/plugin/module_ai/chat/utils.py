from typing import Any

from agno.agent import Agent
from agno.models.openai.like import OpenAILike
from agno.team import Team

from app.config.setting import settings
from app.plugin.module_ai.provider.service import build_headers


def _load_tools() -> list:
    """加载 AI 助手工具（受控只读/导航/报告），供 Agno Agent 使用。"""
    try:
        from app.plugin.module_ai.assistant.tools import TOOL_REGISTRY

        return [t["fn"] for t in TOOL_REGISTRY.values()]
    except Exception:
        return []


class AgnoFactory:
    """Agno 工厂类 - 统一管理 Agent、Team 创建逻辑"""

    AGENT_DESCRIPTION = "你是 AIStation 平台的智能助手，可调用工具查询系统数据、生成报告、导航页面。"
    AGENT_INSTRUCTIONS = [
        "涉及系统数据时必须调用工具获取，禁止编造",
        "需要跳转页面时使用工具返回导航",
        "用简洁中文回答，取数结果可用 Markdown 表格",
    ]
    AGENT_EXPECTED_OUTPUT = "中文回答"
    AGENT_TEMPERATURE = 0.7
    NUM_HISTORY_RUNS = 3

    def _build_model(self, model_config: dict | None):
        mc = model_config or {}
        base_url = mc.get("base_url") or settings.OPENAI_BASE_URL
        kwargs: dict[str, Any] = {
            "id": mc.get("model") or settings.OPENAI_MODEL,
            "api_key": mc.get("api_key") or settings.OPENAI_API_KEY,
            "base_url": base_url,
            "temperature": self.AGENT_TEMPERATURE,
        }
        headers = build_headers(base_url, mc.get("extra_headers"))
        try:
            return OpenAILike(**kwargs, default_headers=headers or None)
        except TypeError:
            # 某些 Agno 版本不支持 default_headers：退回无自定义头
            return OpenAILike(**kwargs)

    def create_agent(
        self,
        user_id: str,
        dept_id: str,
        session_id: str,
        db: Any | None = None,
        model_config: dict | None = None,
    ) -> Team:
        """创建带 Agent 的 Team 实例（使用传入的运行时模型配置，缺省回退 env）。"""
        model = self._build_model(model_config)
        tools = _load_tools()

        agent_kwargs: dict[str, Any] = {
            "id": user_id,
            "name": "aistation_agent",
            "role": "You are a helpful AI assistant",
            "description": self.AGENT_DESCRIPTION,
            "tools": tools,
        }
        try:
            aistation_agent = Agent(**agent_kwargs)
        except Exception:
            aistation_agent = Agent(
                id=user_id, name="aistation_agent", description=self.AGENT_DESCRIPTION, tools=[]
            )

        aistation_team = Team(
            id=dept_id,
            user_id=user_id,
            session_id=session_id,
            model=model,
            members=[aistation_agent],
            instructions=self.AGENT_INSTRUCTIONS,
            expected_output=self.AGENT_EXPECTED_OUTPUT,
            add_datetime_to_context=True,
            add_history_to_context=True,
            markdown=True,
            num_history_runs=self.NUM_HISTORY_RUNS,
            input_schema=None,
            output_schema=None,
            parse_response=True,
            read_chat_history=True,
            db=db,
        )

        return aistation_team
