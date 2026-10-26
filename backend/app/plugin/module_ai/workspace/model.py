"""AI 工作台模型：统一分类（树）+ 定时任务条目。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiWorkspaceCategoryModel(ModelMixin, UserMixin):
    """工作台统一分类（树形，parent_id 支持多级）。"""

    __tablename__ = "ai_workspace_categories"
    __table_args__ = ({"comment": "AI 工作台分类表"},)

    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="分类名称")
    parent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("ai_workspace_categories.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        index=True,
        comment="父分类ID（空为顶级）",
    )
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True, default="", comment="图标")
    color: Mapped[str | None] = mapped_column(String(32), nullable=True, default="", comment="主题色")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序")


class AiWorkspaceCronModel(ModelMixin, UserMixin):
    """工作台定时任务：按统一触发器（cron/interval/date/now）执行绑定的资产（agent/workflow/app）。"""

    __tablename__ = "ai_workspace_cron"
    __table_args__ = ({"comment": "AI 工作台定时任务表"},)

    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="任务名称")
    description: Mapped[str | None] = mapped_column(
        String(512), nullable=True, default="", comment="任务描述"
    )
    trigger: Mapped[str] = mapped_column(
        String(16), nullable=False, default="cron", server_default="cron",
        comment="触发类型 cron/interval/date/now",
    )
    trigger_args: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None, comment="触发参数（cron 5 段 / interval JSON / date 时间）"
    )
    target_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default="agent", comment="执行目标类型 agent/workflow/app"
    )
    target_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="执行目标 ID"
    )
    category_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("ai_workspace_categories.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        index=True,
        comment="所属分类ID",
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否启用")
    last_run_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, comment="上次运行时间"
    )
    next_run_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, comment="下次运行时间"
    )
    # ---- 上次执行结果（卡片上直接能看，不用再翻日志） ----
    last_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default=None, comment="上次结果 success/error"
    )
    last_duration_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="上次耗时（毫秒）"
    )
    last_message: Mapped[str | None] = mapped_column(
        String(512), nullable=True, default=None, comment="上次执行摘要 / 错误信息"
    )
    last_run_id: Mapped[str | None] = mapped_column(
        String(40), nullable=True, default=None, comment="上次执行的 run_id（对应 ai_run_steps）"
    )
    # 连续失败到上限自动停用：避免坏配置每天烧模型调用
    fail_streak: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="连续失败次数（成功清零）"
    )
    auto_disabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
        comment="是否因连续失败被自动停用",
    )
