from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import MappedBase


class UserNotificationModel(MappedBase):
    __tablename__ = "sys_user_notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("sys_user.id", ondelete="CASCADE"), index=True, comment="收件人ID"
    )
    title: Mapped[str] = mapped_column(String(128), comment="通知标题")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="通知内容")
    type: Mapped[str] = mapped_column(
        String(32), default="system",
        comment="类型: training_complete/training_failed/task_assigned/export_complete/system"
    )
    module: Mapped[str] = mapped_column(
        String(32), default="system", comment="模块: train/annotation/system"
    )
    module_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="关联业务ID")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已读")
    created_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
    )
