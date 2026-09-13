from sqlalchemy import Boolean, Integer, String
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
