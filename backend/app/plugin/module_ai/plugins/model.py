"""AI 能力插件模型（能力包，非平台代码插件）。"""
from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiPluginModel(ModelMixin, UserMixin):
    """AI 能力插件：安装后被 Agent 启用的能力包（web_fetch 等）。"""

    __tablename__ = "ai_plugins"
    __table_args__ = ({"comment": "AI 能力插件表"},)

    key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, comment="插件标识（执行器注册 key）"
    )
    label: Mapped[str | None] = mapped_column(
        String(128), nullable=True, default="", comment="显示名"
    )
    kind: Mapped[str] = mapped_column(
        String(32), default="builtin", comment="插件类型: builtin/custom"
    )
    config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="插件配置"
    )
    config_schema: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="配置项 JSON schema"
    )
    executor_ready: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="执行器是否已实现"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="描述"
    )
