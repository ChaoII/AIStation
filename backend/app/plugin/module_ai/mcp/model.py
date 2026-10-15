"""MCP 服务器配置模型。"""
from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiMcpServerModel(ModelMixin, UserMixin):
    """MCP 服务器配置：Agent 运行时通过 agno MCPTools 接入。"""

    __tablename__ = "ai_mcp_servers"
    __table_args__ = ({"comment": "AI MCP 服务器配置表"},)

    name: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, comment="服务器名（唯一）"
    )
    transport: Mapped[str] = mapped_column(
        String(32), default="streamable-http", comment="传输方式: stdio/sse/streamable-http"
    )
    command: Mapped[str | None] = mapped_column(
        String(512), nullable=True, default="", comment="stdio 启动命令"
    )
    args: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="stdio 命令参数数组"
    )
    env: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="stdio 环境变量"
    )
    url: Mapped[str | None] = mapped_column(
        String(512), nullable=True, default="", comment="sse/streamable-http 地址"
    )
    headers: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="自定义请求头"
    )
    auth_type: Mapped[str] = mapped_column(
        String(16), default="none", comment="鉴权: none/bearer/custom"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="描述"
    )
