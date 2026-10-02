"""低代码工作流定义模型。"""
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiWorkflowModel(ModelMixin, UserMixin):
    """AI 工作流：节点 DAG 定义（开始/LLM/工具/知识库/条件/代码/变量/结束）。"""

    __tablename__ = "ai_workflows"
    __table_args__ = ({"comment": "AI 工作流定义表"},)

    name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="工作流名称"
    )
    description: Mapped[str | None] = mapped_column(
        String(512), nullable=True, default="", comment="工作流描述"
    )
    graph: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="节点 DAG（nodes/edges）"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, comment="版本号")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
