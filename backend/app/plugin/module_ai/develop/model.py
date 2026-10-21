"""AI 集成开放平台：应用、调用日志与 MCP 会话模型。

- :class:`AiIntegrationAppModel`：外部平台接入应用（凭证 + 授权能力 + 配额）。
- :class:`AiIntegrationCallLogModel`：调用日志（每次对外 API 调用审计）。
- :class:`AiIntegrationMcpSessionModel`：MCP 工具会话生命周期。

说明：两个审计表直接继承 :class:`MappedBase`（裸基类，无公共列），
因此自行定义 ``id``（Integer PK）与 ``created_time``（DateTime, default=now, index）。
应用表使用 ``ModelMixin, UserMixin``；启停用 ``enabled`` 布尔，不复用 ``ModelMixin.status``。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import MappedBase, ModelMixin, UserMixin


class AiIntegrationAppModel(ModelMixin, UserMixin):
    """AI 集成应用：外部平台接入的凭证、授权能力与配额配置。"""

    __tablename__ = "ai_integration_apps"
    __table_args__ = ({"comment": "AI 集成应用表"},)

    appid: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True,
        comment="应用标识（对外暴露，唯一）",
    )
    appkey_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="AppKey 散列（不存明文）",
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, comment="应用名称（唯一）",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="是否启用（启停开关）",
    )
    expire_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, nullable=True, comment="凭证过期时间（空为永久）",
    )
    capabilities: Mapped[list | None] = mapped_column(
        JSONB, default=list, nullable=False, comment="授权能力列表",
    )
    quota: Mapped[dict | None] = mapped_column(
        JSONB, default=None, nullable=True, comment="配额配置（JSON 对象）",
    )
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="调用是否需要人工审批",
    )
    source_type: Mapped[str] = mapped_column(
        String(16), default="admin", nullable=False, comment="来源类型: admin/self",
    )
    last_call_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, nullable=True, comment="最近一次调用时间",
    )
    call_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="累计调用次数",
    )


class AiIntegrationCallLogModel(MappedBase):
    """AI 集成调用日志：记录每次对外 API 调用的审计信息。"""

    __tablename__ = "ai_integration_call_logs"
    __table_args__ = ({"comment": "AI 集成调用日志表"},)

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="主键ID",
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False, index=True, comment="创建时间",
    )
    app_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_integration_apps.id"), nullable=False, index=True,
        comment="所属应用ID",
    )
    appid: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="应用标识（冗余，便于只读查询）",
    )
    category: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="能力品类: train/agent/chat/bot/embed",
    )
    capability: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="具体能力码",
    )
    log_type: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="日志类型: request/response/error",
    )
    method: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="HTTP 方法",
    )
    transport: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="传输方式: http/sse/ws",
    )
    session_id: Mapped[str | None] = mapped_column(
        String(64), default=None, nullable=True, comment="关联会话ID",
    )
    client_info: Mapped[str | None] = mapped_column(
        String(128), default=None, nullable=True, comment="客户端信息",
    )
    request_path: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="请求路径",
    )
    request_body: Mapped[dict | None] = mapped_column(
        JSONB, default=None, nullable=True, comment="请求体（JSON）",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="调用状态: success/failed/denied",
    )
    error: Mapped[str | None] = mapped_column(
        String(255), default=None, nullable=True, comment="错误信息",
    )
    latency_ms: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="耗时（毫秒）",
    )
    cost_tokens: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="消耗 token 数",
    )
    result_summary: Mapped[str | None] = mapped_column(
        String(512), default=None, nullable=True, comment="结果摘要",
    )


class AiIntegrationMcpSessionModel(MappedBase):
    """AI 集成 MCP 会话：记录 MCP 工具会话的生命周期与统计。"""

    __tablename__ = "ai_integration_mcp_sessions"
    __table_args__ = ({"comment": "AI 集成 MCP 会话表"},)

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="主键ID",
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False, index=True, comment="创建时间",
    )
    app_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_integration_apps.id"), nullable=False, index=True,
        comment="所属应用ID",
    )
    appid: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="应用标识（冗余）",
    )
    session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="会话ID",
    )
    transport: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="传输方式: stdio/sse/streamable-http",
    )
    client_info: Mapped[str | None] = mapped_column(
        String(128), default=None, nullable=True, comment="客户端信息",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="会话开始时间",
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, nullable=True, comment="会话结束时间",
    )
    duration_s: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="会话时长（秒）",
    )
    tool_calls: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="会话内工具调用次数",
    )
    close_reason: Mapped[str | None] = mapped_column(
        String(64), default=None, nullable=True, comment="关闭原因",
    )
