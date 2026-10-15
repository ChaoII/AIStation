"""AI 智能体实体与分类模型。"""
from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiAgentCategoryModel(ModelMixin, UserMixin):
    """智能体分类（树形，parent_id 支持层级）。"""

    __tablename__ = "ai_agent_categories"
    __table_args__ = ({"comment": "AI 智能体分类表"},)

    name: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="分类名称"
    )
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ai_agent_categories.id", ondelete="SET NULL"),
        nullable=True, default=None, comment="父分类ID",
    )
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序")


class AiAgentModel(ModelMixin, UserMixin):
    """AI 智能体：整合模型/提示词/工具/工作流/知识库/技能等配置。"""

    __tablename__ = "ai_agents"
    __table_args__ = ({"comment": "AI 智能体表"},)

    agent_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="智能体名称"
    )
    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ai_agent_categories.id", ondelete="SET NULL"),
        nullable=True, default=None, comment="分类ID",
    )
    agent_role: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default="", comment="角色描述"
    )
    model_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="绑定模型ID"
    )
    prompt_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="绑定提示词ID"
    )
    temperature: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=None, comment="温度（覆盖模型默认）"
    )
    workflow_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="绑定低代码工作流ID"
    )
    tool_ids: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="工具名列表"
    )
    skill_ids: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="技能ID列表（技能广场）"
    )
    knowledge_ids: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="知识库ID列表（RAG）"
    )
    mcp_ids: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="MCP 服务器ID列表"
    )
    capabilities: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
        comment="能力列表：功能标志（query/grounding/knowledge）与本体能力编码（本体函数/对象动作 code）共用",
    )
    query_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否启用智能问数"
    )
    query_datasource: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default="system", comment="问数数据源/场景"
    )
    input_schema: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="入参 JSON schema"
    )
    avatar: Mapped[str | None] = mapped_column(
        String(256), nullable=True, default="", comment="头像/Logo"
    )
    color: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default="", comment="主题色"
    )
    markdown: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否 Markdown 输出")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
