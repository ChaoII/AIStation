from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiModelModel(ModelMixin, UserMixin):
    """大模型配置：归属提供商 + 具体模型。"""

    __tablename__ = "ai_models"
    __table_args__ = ({"comment": "大模型配置表"},)

    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment="配置名称")
    provider: Mapped[str] = mapped_column(
        String(32), default="openai_compatible", comment="协议（兼容旧字段）"
    )
    provider_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True, comment="所属提供商ID"
    )
    usage: Mapped[str] = mapped_column(
        String(16), default="chat", comment="用途: chat/assistant/embedding"
    )
    capabilities: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="能力标签: chat/tool/vision"
    )
    context_window: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="上下文窗口(tokens)"
    )
    base_url: Mapped[str] = mapped_column(String(512), default="", comment="API 基址")
    api_key: Mapped[str] = mapped_column(String(512), default="", comment="API Key")
    model: Mapped[str] = mapped_column(String(128), default="", comment="模型名")
    temperature: Mapped[float] = mapped_column(Float, default=0.3, comment="温度")
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048, comment="最大 token")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否默认")
    extra_headers: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="自定义请求头（网关鉴权等）"
    )
