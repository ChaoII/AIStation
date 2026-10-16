"""AI 能力市场模型：市场商品、安装/收藏关系、点对点分享。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin


class AiMarketItemModel(ModelMixin):
    """市场商品：工具/技能/MCP/插件统一橱窗条目。"""

    __tablename__ = "ai_market_items"
    __table_args__ = ({"comment": "AI 能力市场商品表"},)

    asset_type: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="资产类型: tool/skill/mcp/plugin"
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="商品名（同类型内唯一，业务层校验）"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="商品描述"
    )
    icon: Mapped[str | None] = mapped_column(
        String(256), nullable=True, default="", comment="图标（emoji 或图片URL）"
    )
    category: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default="", comment="市场分类"
    )
    tags: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="标签数组"
    )
    version: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default="1.0", comment="版本（展示）"
    )
    owner_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="提交人（官方内置为 NULL）"
    )
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, comment="平台内置")
    featured: Mapped[bool] = mapped_column(Boolean, default=False, comment="精选")
    status: Mapped[str] = mapped_column(
        String(16), default="pending", comment="状态: draft/pending/approved/rejected/offline"
    )
    payload: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="真实资产快照（按 asset_type 结构不同）"
    )
    source_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="提交时来源真实记录 id（仅记录）"
    )
    install_count: Mapped[int] = mapped_column(Integer, default=0, comment="安装次数")
    favorite_count: Mapped[int] = mapped_column(Integer, default=0, comment="收藏次数")
    audit_remark: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default="", comment="审核意见"
    )
    audit_user: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="审核人"
    )
    audit_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="审核时间"
    )


class AiMarketRelationModel(ModelMixin):
    """用户与市场商品的关系：安装/收藏。"""

    __tablename__ = "ai_market_relations"
    __table_args__ = ({"comment": "AI 市场用户关系表（安装/收藏）"},)

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sys_user.id"), nullable=False, comment="用户"
    )
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_market_items.id"), nullable=False, comment="商品"
    )
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="关系类型: installed/favorited"
    )


class AiMarketShareModel(ModelMixin):
    """用户间点对点分享记录。"""

    __tablename__ = "ai_market_shares"
    __table_args__ = ({"comment": "AI 市场点对点分享表"},)

    item_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ai_market_items.id"), nullable=True, default=None, comment="市场商品（分享市场商品时二选一）"
    )
    asset_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default=None, comment="资产类型: tool/skill/mcp/plugin（分享个人资产时二选一）"
    )
    payload: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="个人资产快照（分享个人资产时）"
    )
    asset_name: Mapped[str | None] = mapped_column(
        String(128), nullable=True, default=None, comment="个人资产名（分享记录快照）"
    )
    asset_icon: Mapped[str | None] = mapped_column(
        String(256), nullable=True, default=None, comment="个人资产图标（分享记录快照）"
    )
    source_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="来源真实资产 id（仅记录）"
    )
    from_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sys_user.id"), nullable=False, comment="分享人"
    )
    to_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sys_user.id"), nullable=False, comment="接收人"
    )
    status: Mapped[str] = mapped_column(
        String(16), default="pending", comment="状态: pending/accepted/rejected"
    )
    message: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default="", comment="留言"
    )
