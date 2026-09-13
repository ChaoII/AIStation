from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiModelModel(ModelMixin, UserMixin):
    """大模型配置：OpenAI 兼容协议的多模型管理。"""

    __tablename__ = "ai_models"
    __table_args__ = ({"comment": "大模型配置表"},)

    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment="配置名称")
    provider: Mapped[str] = mapped_column(
        String(32), default="openai_compatible", comment="提供方协议"
    )
    base_url: Mapped[str] = mapped_column(String(512), default="", comment="API 基址")
    api_key: Mapped[str] = mapped_column(String(512), default="", comment="API Key")
    model: Mapped[str] = mapped_column(String(128), default="", comment="模型名")
    temperature: Mapped[float] = mapped_column(Float, default=0.3, comment="温度")
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048, comment="最大 token")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否默认")
