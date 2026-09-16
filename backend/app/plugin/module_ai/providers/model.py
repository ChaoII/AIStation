from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiProviderModel(ModelMixin, UserMixin):
    """大模型提供商（OpenAI/Anthropic/Ollama/自定义兼容端点）。"""

    __tablename__ = "ai_providers"
    __table_args__ = ({"comment": "大模型提供商表"},)

    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment="名称")
    protocol: Mapped[str] = mapped_column(
        String(32), default="openai", comment="协议: openai/anthropic/ollama/custom"
    )
    base_url: Mapped[str] = mapped_column(String(512), default="", comment="API 基址")
    api_key: Mapped[str] = mapped_column(String(512), default="", comment="API Key")
    extra_headers: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="自定义请求头"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
