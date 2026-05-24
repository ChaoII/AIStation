from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import MappedBase, ModelMixin, UserMixin


class AlarmRuleModel(ModelMixin, UserMixin):
    __tablename__ = "video_alarm_rules"
    __table_args__ = ({'comment': '告警规则表'})
    __loader_options__ = ["camera", "creator"]

    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="规则名称")
    camera_id: Mapped[int] = mapped_column(Integer, ForeignKey("video_cameras.id", ondelete="CASCADE"), nullable=False, index=True)
    camera: Mapped[Optional["CameraModel"]] = relationship(lazy="selectin")

    alarm_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="告警类型: MOTION/LINE_CROSSING/INTRUSION/FACE_DETECT/...")
    algorithm_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="算法任务ID")
    severity: Mapped[str] = mapped_column(String(16), default="WARNING", comment="严重级别: INFO/WARNING/CRITICAL")

    detect_region: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="检测区域(多边形坐标)")
    sensitivity: Mapped[int] = mapped_column(Integer, default=50, comment="灵敏度 1-100")
    interval_seconds: Mapped[int] = mapped_column(Integer, default=30, comment="告警间隔(秒)")

    notify_channels: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="通知方式: [WS_PUSH, SMS, EMAIL]")

    schedule_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="生效时间段")
    status: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")


class AlarmRecordModel(MappedBase):
    __tablename__ = "video_alarm_records"
    __table_args__ = ({'comment': '告警记录表'})

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(Integer, ForeignKey("video_cameras.id", ondelete="CASCADE"), nullable=False, index=True)
    camera: Mapped[Optional["CameraModel"]] = relationship(lazy="selectin")
    rule_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("video_alarm_rules.id", ondelete="SET NULL"), nullable=True)
    rule: Mapped[Optional["AlarmRuleModel"]] = relationship(lazy="selectin")

    alarm_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="告警类型")
    severity: Mapped[str] = mapped_column(String(16), default="WARNING", comment="严重级别")

    snapshot_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="告警截图")
    video_clip_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="告警视频片段")

    alarm_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=datetime.now, comment="告警时间")
    confirm_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="确认时间")
    confirm_user: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="确认人")

    status: Mapped[str] = mapped_column(String(16), default="PENDING", comment="状态: PENDING/CONFIRMED/IGNORED/FALSE_ALARM")
    ai_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="AI检测原始数据")

    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=datetime.now)
