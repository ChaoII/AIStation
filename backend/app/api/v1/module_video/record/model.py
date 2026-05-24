from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import MappedBase, ModelMixin, UserMixin


class RecordPlanModel(ModelMixin, UserMixin):
    __tablename__ = "video_record_plans"
    __table_args__ = ({'comment': '录制计划表'})
    __loader_options__ = ["camera", "creator"]

    camera_id: Mapped[int] = mapped_column(Integer, ForeignKey("video_cameras.id", ondelete="CASCADE"), nullable=False, index=True)
    camera: Mapped[Optional["CameraModel"]] = relationship(lazy="selectin")

    plan_type: Mapped[str] = mapped_column(String(16), default="CONTINUOUS", comment="计划类型: CONTINUOUS/SCHEDULE/EVENT/ALARM")
    schedule_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="时间段配置")

    pre_record_sec: Mapped[int] = mapped_column(Integer, default=5, comment="预录秒数")
    post_record_sec: Mapped[int] = mapped_column(Integer, default=5, comment="延录秒数")
    storage_days: Mapped[int] = mapped_column(Integer, default=30, comment="存储天数")

    stream_type: Mapped[str] = mapped_column(String(16), default="MAIN", comment="录制码流: MAIN/SUB")
    status: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")


class RecordFileModel(MappedBase):
    __tablename__ = "video_record_files"
    __table_args__ = ({'comment': '录制文件表'})

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(Integer, ForeignKey("video_cameras.id", ondelete="CASCADE"), nullable=False, index=True)
    camera: Mapped[Optional["CameraModel"]] = relationship(lazy="selectin")

    stream_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="ZLM stream_id")
    file_path: Mapped[str] = mapped_column(String(512), nullable=False, comment="文件路径")
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="文件大小(bytes)")
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="时长(秒)")

    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间")
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间")
    record_type: Mapped[str] = mapped_column(String(16), default="CONTINUOUS", comment="录制类型: CONTINUOUS/ALARM/MANUAL")
    format: Mapped[str] = mapped_column(String(8), default="mp4", comment="文件格式: mp4/flv/hls")

    status: Mapped[str] = mapped_column(String(16), default="COMPLETED", comment="状态: RECORDING/COMPLETED/CORRUPTED")

    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=datetime.now)
