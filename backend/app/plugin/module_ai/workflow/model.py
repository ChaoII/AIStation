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
    share_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None, index=True, comment="公开分享令牌（受限运行）"
    )


class AiWorkflowVersionModel(ModelMixin, UserMixin):
    """工作流版本快照：保存某一时刻的 DAG 定义，用于发布与回滚。"""

    __tablename__ = "ai_workflow_versions"
    __table_args__ = ({"comment": "AI 工作流版本表"},)

    workflow_id: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="所属工作流 ID"
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="版本号")
    graph: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="该版本的节点 DAG"
    )
    remark: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default="", comment="版本说明"
    )
    published: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否已发布（线上版本）"
    )


class AiWorkflowRunLogModel(ModelMixin, UserMixin):
    """工作流运行历史：记录每次运行的输入/输出/报错与节点执行轨迹。"""

    __tablename__ = "ai_workflow_run_logs"
    __table_args__ = ({"comment": "AI 工作流运行历史表"},)

    workflow_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="所属工作流 ID"
    )
    status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default="", comment="运行状态 success/error/pending"
    )
    run_input: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="本次运行输入（变量）"
    )
    run_output: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="本次运行输出/回复"
    )
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True, default=None, comment="报错信息")
    node_trace: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="节点执行轨迹（node-status 快照）"
    )
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, comment="运行耗时(ms)")
