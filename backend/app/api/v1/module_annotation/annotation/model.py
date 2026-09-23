
from sqlalchemy import ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AnnotationRecordModel(ModelMixin, UserMixin):
    __tablename__ = "annotation_record"

    task_id: Mapped[int] = mapped_column(ForeignKey("annotation_task.id"), comment="任务ID")
    # 图片/视频/文本/音频/时间序列五者互斥：图片标注用 image_id，视频标注用 video_id + frame_index，
    # 文本标注用 document_id，音频标注用 audio_id，时间序列标注用 time_series_id。
    image_id: Mapped[int | None] = mapped_column(
        ForeignKey("annotation_image.id"), nullable=True, comment="图片ID"
    )
    video_id: Mapped[int | None] = mapped_column(
        ForeignKey("annotation_video.id"), nullable=True, comment="视频ID"
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("annotation_document.id"), nullable=True, comment="文档ID(文本标注)"
    )
    audio_id: Mapped[int | None] = mapped_column(
        ForeignKey("annotation_audio.id"), nullable=True, comment="音频ID(音频事件标注)"
    )
    time_series_id: Mapped[int | None] = mapped_column(
        ForeignKey("annotation_time_series.id"),
        nullable=True,
        comment="时间序列ID(时间序列事件标注)",
    )
    frame_index: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="帧序号(视频标注)")
    annotation_data: Mapped[dict] = mapped_column(JSONB, comment="标注 JSON 数据")
    version: Mapped[int] = mapped_column(Integer, default=1, comment="版本号")

    __table_args__ = (
        Index("ix_annotation_record_task_image_version", "task_id", "image_id", "version"),
        Index(
            "ix_annotation_record_task_video_frame_version",
            "task_id", "video_id", "frame_index", "version",
        ),
        Index(
            "ix_annotation_record_task_document_version",
            "task_id", "document_id", "version",
        ),
        Index(
            "ix_annotation_record_task_audio_version",
            "task_id", "audio_id", "version",
        ),
        Index(
            "ix_annotation_record_task_timeseries_version",
            "task_id", "time_series_id", "version",
        ),
    )

    __mapper_args__ = {"eager_defaults": True}
