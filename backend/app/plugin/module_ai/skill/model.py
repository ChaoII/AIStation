"""AI 技能（技能广场）模型。"""
from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiSkillModel(ModelMixin, UserMixin):
    """技能广场：可复用能力包，按 skill_type 注入 Agent/工作流。"""

    __tablename__ = "ai_skills"
    __table_args__ = ({"comment": "AI 技能广场表"},)

    name: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, comment="技能名称"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="简要描述"
    )
    content: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="技能内容（Markdown 指令/说明）"
    )
    skill_type: Mapped[str] = mapped_column(
        String(32), default="tool", comment="技能类型: instruction/tool/custom"
    )
    category: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default="", comment="分类标签"
    )
    author: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default="", comment="创建者"
    )
    version: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default="1.0", comment="版本号"
    )
    scripts: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="可执行脚本字典"
    )
    config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="初始化参数 JSON"
    )
    icon: Mapped[str | None] = mapped_column(
        String(256), nullable=True, default="", comment="图标（emoji 或图片URL）"
    )
    featured: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否精选")
    install_count: Mapped[int] = mapped_column(Integer, default=0, comment="安装次数")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序号")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
