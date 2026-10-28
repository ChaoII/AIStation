"""AI 资产嵌入令牌模型。

嵌入域从「AI 集成开放平台」剥离后，令牌**独立绑定资产**（``kind + target_id``），
不再依附 ``app_id``/``appid``。与开发平台应用无关，供工作台卡片「嵌入」消费单个
agent/工作流。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin


class AiAssetAccessTokenModel(ModelMixin):
    """资产嵌入令牌：短期 access_token，只存散列、独立绑定嵌入目标。

    - 明文仅在签发响应返回一次，库内只存 ``token_hash``（sha256）。
    - ``kind`` + ``target_id`` 把令牌收缩到单资产（嵌入代码公开暴露，最小权限）。
    - ``issued_by`` 标识签发来源（工作台/管理端）。
    """

    __tablename__ = "ai_asset_access_tokens"
    __table_args__ = ({"comment": "AI 资产嵌入令牌表"},)

    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="嵌入形态: agent/workflow"
    )
    target_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="嵌入目标ID"
    )
    token_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
        comment="令牌散列（sha256，不存明文）",
    )
    issued_by: Mapped[str] = mapped_column(
        String(16), default="admin", nullable=False, comment="签发来源: admin/workbench"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="过期时间")
    revoked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否已吊销"
    )
    use_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="累计使用次数"
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, nullable=True, comment="最后使用时间"
    )
    allow_domains: Mapped[str | None] = mapped_column(
        String(1024), default=None, nullable=True, comment="允许来源域名（逗号分隔，空=不限）"
    )
    allow_ips: Mapped[str | None] = mapped_column(
        String(1024), default=None, nullable=True, comment="允许来源IP/网段（逗号分隔，空=不限）"
    )


class AiAssetEmbedSessionModel(ModelMixin):
    """资产嵌入会话映射：客户端 ``sid`` ↔ 平台会话（TTL 24 小时）。

    ``(kind, target_id, sid)`` 复合唯一，防跨资产/跨目标 sid 撞号串会话；
    ``session_id`` 指向 ``ai_assistant_sessions.id``（复用平台会话存储）。
    与开放平台应用无关（不再绑定 app_id）。
    """

    __tablename__ = "ai_asset_embed_sessions"
    __table_args__ = (
        UniqueConstraint("kind", "target_id", "sid", name="uq_ai_asset_embed_sessions_asset_sid"),
        {"comment": "AI 资产嵌入会话映射表"},
    )

    kind: Mapped[str] = mapped_column(String(16), nullable=False, comment="嵌入形态")
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="嵌入目标ID")
    sid: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="客户端会话标识")
    session_id: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="平台会话ID（ai_assistant_sessions.id）"
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="映射过期时间")
    last_active_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="最后活跃时间")


class AiAssetEmbedLogModel(ModelMixin):
    """资产嵌入调用审计（工作台卡片「嵌入」弹窗展示）。

    - 每次 ``/ai/embed/run`` 在流结束时写入（成功/失败都写）。
    - 与开发平台调用日志（``ai_integration_call_logs``）解耦，嵌入域的审计只归这里。
    """

    __tablename__ = "ai_asset_embed_logs"
    __table_args__ = ({"comment": "AI 资产嵌入调用审计表"},)

    kind: Mapped[str] = mapped_column(String(16), nullable=False, comment="嵌入形态")
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="嵌入目标ID")
    session_id: Mapped[str] = mapped_column(String(64), default="", comment="平台会话ID（字符串）")
    sid: Mapped[str] = mapped_column(String(64), default="", comment="客户端会话标识")
    message: Mapped[str] = mapped_column(String(120), default="", comment="用户消息摘要（截断）")
    result_status: Mapped[str] = mapped_column(
        String(16), default="success", comment="结果: success/error/denied"
    )
    error: Mapped[str | None] = mapped_column(String(250), default=None, nullable=True, comment="错误信息")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, comment="耗时毫秒")
    token_hash12: Mapped[str] = mapped_column(String(12), default="", comment="令牌散列前12位（脱敏）")
    token_id: Mapped[int | None] = mapped_column(
        Integer, default=None, nullable=True, index=True, comment="关联 ai_asset_access_tokens.id"
    )
    client_ip: Mapped[str] = mapped_column(
        String(64), default="", nullable=False, comment="调用来源IP"
    )
