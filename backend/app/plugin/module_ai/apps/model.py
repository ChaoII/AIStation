from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiAppModel(ModelMixin, UserMixin):
    """AI 应用：模型 + 提示词 + 工具集 + 输出格式 + 入参定义，可启停。"""

    __tablename__ = "ai_apps"
    __table_args__ = ({"comment": "AI 应用表"},)

    name: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, comment="应用名（唯一）"
    )
    category_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("ai_workspace_categories.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        index=True,
        comment="工作台分类ID",
    )
    icon: Mapped[str] = mapped_column(String(64), default="", comment="图标")
    model_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="绑定模型ID")
    prompt_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="绑定提示词ID")
    tools: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="工具名列表（内置或自定义 HTTP）"
    )
    output_format: Mapped[str] = mapped_column(
        String(16), default="text", comment="输出格式: text/table/report"
    )
    input_schema: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="入参 JSON schema"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    app_type: Mapped[str] = mapped_column(
        String(16), default="chat", comment="组件类型: chat/agent/workflow/kb"
    )
    kb_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="绑定知识库ID(类型=kb)"
    )
    workflow_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="绑定工作流ID(有工作流时)"
    )
    temperature: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=None, comment="温度(留空用模型默认)"
    )
    max_tokens: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="最大输出token(留空用模型默认)"
    )
    context_window: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="上下文窗口(可达性提示)"
    )
    system_prompt: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None, comment="自定义系统提示词(覆盖prompt_id)"
    )
    tags: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="标签"
    )
    memory: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否开启多轮记忆")
    timeout: Mapped[int] = mapped_column(Integer, default=60, comment="超时(秒)")
