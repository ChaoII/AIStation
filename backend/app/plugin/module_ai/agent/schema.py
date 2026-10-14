"""智能体实体与分类的 Pydantic 模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AiAgentCreateSchema(BaseModel):
    agent_name: str = Field(..., max_length=128)
    category_id: int | None = None
    agent_role: str | None = Field(default=None, max_length=255)
    description: str | None = None
    model_id: int | None = None
    prompt_id: int | None = None
    temperature: float | None = None
    workflow_id: int | None = None
    tool_ids: list[str] = Field(default_factory=list)
    skill_ids: list[int] = Field(default_factory=list)
    knowledge_ids: list[int] = Field(default_factory=list)
    capabilities: list[str] = Field(
        default_factory=list,
        description="能力列表：功能标志（query/grounding/knowledge）+ 本体能力编码（本体函数/对象动作 code）",
    )
    query_enabled: bool = False
    query_datasource: str | None = Field(default="system", max_length=64)
    input_schema: dict | None = None
    avatar: str | None = Field(default=None, max_length=256)
    color: str | None = Field(default=None, max_length=32)
    markdown: bool = True
    enabled: bool = True
    order: int = 0


class AiAgentUpdateSchema(BaseModel):
    agent_name: str | None = Field(default=None, max_length=128)
    category_id: int | None = None
    agent_role: str | None = Field(default=None, max_length=255)
    description: str | None = None
    model_id: int | None = None
    prompt_id: int | None = None
    temperature: float | None = None
    workflow_id: int | None = None
    tool_ids: list[str] | None = None
    skill_ids: list[int] | None = None
    knowledge_ids: list[int] | None = None
    capabilities: list[str] | None = None
    query_enabled: bool | None = None
    query_datasource: str | None = Field(default=None, max_length=64)
    input_schema: dict | None = None
    avatar: str | None = Field(default=None, max_length=256)
    color: str | None = Field(default=None, max_length=32)
    markdown: bool | None = None
    enabled: bool | None = None
    order: int | None = None


class AiAgentRunSchema(BaseModel):
    """运行智能体：messages + 变量 + 会话。"""

    messages: list[dict] = Field(default_factory=list)
    variables: dict | None = None
    session_id: int | None = None


class AiAgentSkillBindSchema(BaseModel):
    """安装/卸载技能到智能体。"""

    skill_id: int = Field(..., description="技能 ID")


class AiAgentCategoryCreateSchema(BaseModel):
    name: str = Field(..., max_length=64)
    parent_id: int | None = None
    sort: int = 0


class AiAgentCategoryUpdateSchema(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    parent_id: int | None = None
    sort: int | None = None
