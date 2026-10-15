from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiToolModel(ModelMixin, UserMixin):
    """AI 工具：内置工具开关 + 自定义 HTTP 工具（零代码扩展）+ Python 脚本工具。"""

    __tablename__ = "ai_tools"
    __table_args__ = ({"comment": "AI 工具表"},)

    name: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, comment="工具名（唯一）"
    )
    kind: Mapped[str] = mapped_column(
        String(16), default="builtin", comment="类型: builtin/http/script"
    )
    source: Mapped[str] = mapped_column(
        String(16), default="system", comment="来源: system/agno/http/script"
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
    body_type: Mapped[str] = mapped_column(
        String(16), default="json", comment="HTTP 请求体类型: none/json/form-data"
    )
    params_schema: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="入参 JSON schema"
    )
    code: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="Python 脚本源码（kind=script）"
    )
    timeout: Mapped[int] = mapped_column(Integer, default=10, comment="脚本执行超时（秒）")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
