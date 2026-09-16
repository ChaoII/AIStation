from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiToolModel(ModelMixin, UserMixin):
    """AI 工具：内置工具开关 + 自定义 HTTP 工具（零代码扩展）。"""

    __tablename__ = "ai_tools"
    __table_args__ = ({"comment": "AI 工具表"},)

    name: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, comment="工具名（唯一）"
    )
    kind: Mapped[str] = mapped_column(
        String(16), default="builtin", comment="类型: builtin/http"
    )
    source: Mapped[str] = mapped_column(
        String(16), default="system", comment="来源: system/agno/http"
    )
    config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="运行配置（API Key / 自定义参数）"
    )
    method: Mapped[str] = mapped_column(String(8), default="GET", comment="HTTP 方法")
    url: Mapped[str] = mapped_column(
        String(512), default="", comment="请求地址，支持 {key} 路径占位"
    )
    headers: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="自定义请求头"
    )
    params_schema: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="入参 JSON schema"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
