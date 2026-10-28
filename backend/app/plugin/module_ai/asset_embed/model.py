"""AI 资产嵌入令牌模型。

嵌入域从「AI 集成开放平台」剥离后，令牌**独立绑定资产**（``kind + target_id``），
不再依附 ``app_id``/``appid``。与开发平台应用无关，供工作台卡片「嵌入」消费单个
agent/工作流。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
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
