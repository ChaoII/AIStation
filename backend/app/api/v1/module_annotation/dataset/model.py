import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import ModelMixin, UserMixin


class AnnotationType(str, enum.Enum):
    DETECTION = "detection"
    ROTATED_DETECTION = "rotated_detection"
    SEGMENTATION = "segmentation"
    SEMANTIC_SEGMENTATION = "semantic_segmentation"
    POLYLINE = "polyline"
    PANOPTIC_SEGMENTATION = "panoptic_segmentation"
    CUBOID = "cuboid"
    KEYPOINT = "keypoint"
    OCR = "ocr"
    CLASSIFICATION = "classification"
    VIDEO_DETECTION = "video_detection"
    VIDEO_EVENT = "video_event"
    TEXT_NER = "text_ner"
    AUDIO_EVENT = "audio_event"
    TIME_SERIES_EVENT = "time_series_event"


class DatasetStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class DatasetModel(ModelMixin, UserMixin):
    __tablename__ = "annotation_dataset"

    name: Mapped[str] = mapped_column(String(128), comment="数据集名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    image_count: Mapped[int] = mapped_column(Integer, default=0, comment="图片总数")
    annotated_count: Mapped[int] = mapped_column(Integer, default=0, comment="已标注图片数")
    video_count: Mapped[int] = mapped_column(Integer, default=0, comment="视频总数")
    document_count: Mapped[int] = mapped_column(Integer, default=0, comment="文档总数")
    audio_count: Mapped[int] = mapped_column(Integer, default=0, comment="音频总数")
    time_series_count: Mapped[int] = mapped_column(Integer, default=0, comment="时间序列总数")

    images = relationship("AnnotationImageModel", back_populates="dataset", lazy="dynamic")
    videos = relationship("AnnotationVideoModel", back_populates="dataset", lazy="dynamic")
    documents = relationship("AnnotationDocumentModel", back_populates="dataset", lazy="dynamic")
    audios = relationship("AnnotationAudioModel", back_populates="dataset", lazy="dynamic")
    time_series = relationship(
        "AnnotationTimeSeriesModel", back_populates="dataset", lazy="dynamic"
    )
    tasks = relationship("AnnotationTaskModel", back_populates="dataset", lazy="dynamic")


class ImageStatus(str, enum.Enum):
    UNANNOTATED = "unannotated"
    IN_PROGRESS = "in_progress"
    ANNOTATED = "annotated"


class AnnotationImageModel(ModelMixin, UserMixin):
    __tablename__ = "annotation_image"

    dataset_id: Mapped[int] = mapped_column(ForeignKey("annotation_dataset.id"), comment="数据集ID")
    filename: Mapped[str] = mapped_column(String(255), comment="原文件名")
    object_key: Mapped[str] = mapped_column(String(512), comment="RustFS 中的 key")
    thumbnail_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="RustFS 缩略图 key"
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="图片内容哈希(sha256)，用于去重"
    )
    width: Mapped[int] = mapped_column(Integer, default=0, comment="图片宽度")
    height: Mapped[int] = mapped_column(Integer, default=0, comment="图片高度")
    status: Mapped[ImageStatus] = mapped_column(
        Enum(ImageStatus), default=ImageStatus.UNANNOTATED, comment="标注状态"
    )
    locked_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="锁定用户ID")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="锁定时间")
    annotation_count: Mapped[int] = mapped_column(Integer, default=0, comment="标注数量")

    dataset = relationship("DatasetModel", back_populates="images")

    __table_args__ = (
        Index("ix_annotation_image_dataset_status", "dataset_id", "status"),
        Index("ix_annotation_image_dataset_hash", "dataset_id", "content_hash"),
    )


class AnnotationVideoModel(ModelMixin, UserMixin):
    __tablename__ = "annotation_video"

    dataset_id: Mapped[int] = mapped_column(ForeignKey("annotation_dataset.id"), comment="数据集ID")
    name: Mapped[str] = mapped_column(String(255), comment="原文件名")
    object_key: Mapped[str] = mapped_column(String(512), comment="RustFS key")
    width: Mapped[int] = mapped_column(Integer, default=0, comment="宽度")
    height: Mapped[int] = mapped_column(Integer, default=0, comment="高度")
    duration: Mapped[float] = mapped_column(Float, default=0.0, comment="时长(秒)")
    fps: Mapped[float] = mapped_column(Float, default=0.0, comment="帧率")
    frame_count: Mapped[int] = mapped_column(Integer, default=0, comment="总帧数")
    thumbnail_key: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="缩略图key")
    status: Mapped[ImageStatus] = mapped_column(
        Enum(ImageStatus), default=ImageStatus.UNANNOTATED, comment="标注状态"
    )
    locked_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="锁定用户ID")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="锁定时间")
    annotation_count: Mapped[int] = mapped_column(Integer, default=0, comment="已标注帧数")

    dataset = relationship("DatasetModel", back_populates="videos")

    __table_args__ = (
        Index("ix_annotation_video_dataset_status", "dataset_id", "status"),
    )


class AnnotationDocumentModel(ModelMixin, UserMixin):
    __tablename__ = "annotation_document"

    dataset_id: Mapped[int] = mapped_column(ForeignKey("annotation_dataset.id"), comment="数据集ID")
    filename: Mapped[str] = mapped_column(String(255), comment="原文件名")
    object_key: Mapped[str] = mapped_column(String(512), comment="RustFS key")
    content_hash: Mapped[str] = mapped_column(String(64), comment="内容哈希(sha256)，用于去重")
    encoding: Mapped[str] = mapped_column(String(32), comment="探测到的原始编码")
    character_count: Mapped[int] = mapped_column(Integer, default=0, comment="解码后字符数(UTF-16 code unit)")
    line_count: Mapped[int] = mapped_column(Integer, default=0, comment="行数")
    status: Mapped[ImageStatus] = mapped_column(
        Enum(ImageStatus), default=ImageStatus.UNANNOTATED, comment="标注状态"
    )
    locked_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="锁定用户ID")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="锁定时间")
    annotation_count: Mapped[int] = mapped_column(Integer, default=0, comment="已标注数量")

    dataset = relationship("DatasetModel", back_populates="documents")

    __table_args__ = (
        Index("ix_annotation_document_dataset_status", "dataset_id", "status"),
        Index("ix_annotation_document_dataset_hash", "dataset_id", "content_hash"),
    )


class AnnotationAudioModel(ModelMixin, UserMixin):
    __tablename__ = "annotation_audio"

    dataset_id: Mapped[int] = mapped_column(ForeignKey("annotation_dataset.id"), comment="所属数据集")
    name: Mapped[str] = mapped_column(String(255), comment="原文件名")
    object_key: Mapped[str] = mapped_column(String(512), comment="RustFS key")
    duration: Mapped[float] = mapped_column(Float, default=0.0, comment="时长(秒)")
    sample_rate: Mapped[int] = mapped_column(Integer, default=0, comment="采样率(Hz)")
    channels: Mapped[int] = mapped_column(Integer, default=0, comment="声道数")
    bitrate: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="码率(kbps)")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, comment="文件字节数")
    status: Mapped[ImageStatus] = mapped_column(
        Enum(ImageStatus), default=ImageStatus.UNANNOTATED, comment="标注状态"
    )
    locked_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="锁定用户ID")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="锁定时间")
    annotation_count: Mapped[int] = mapped_column(Integer, default=0, comment="已标事件数")

    dataset = relationship("DatasetModel", back_populates="audios")

    __table_args__ = (
        Index("ix_annotation_audio_dataset_status", "dataset_id", "status"),
    )


class AnnotationTimeSeriesModel(ModelMixin, UserMixin):
    __tablename__ = "annotation_time_series"

    dataset_id: Mapped[int] = mapped_column(ForeignKey("annotation_dataset.id"), comment="所属数据集")
    name: Mapped[str] = mapped_column(String(255), comment="原文件名")
    object_key: Mapped[str] = mapped_column(String(512), comment="RustFS key")
    time_column: Mapped[str] = mapped_column(String(64), comment="时间列名")
    value_columns: Mapped[list[str]] = mapped_column(JSONB, comment="数值列名列表")
    row_count: Mapped[int] = mapped_column(Integer, default=0, comment="数据行数")
    time_unit: Mapped[str] = mapped_column(String(8), comment="时间单位(秒s/毫秒ms)")
    start_time: Mapped[float | None] = mapped_column(Float, nullable=True, comment="时间范围起点")
    end_time: Mapped[float | None] = mapped_column(Float, nullable=True, comment="时间范围终点")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, comment="文件字节数")
    status: Mapped[ImageStatus] = mapped_column(
        Enum(ImageStatus), default=ImageStatus.UNANNOTATED, comment="标注状态"
    )
    locked_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="锁定用户ID")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="锁定时间")
    annotation_count: Mapped[int] = mapped_column(Integer, default=0, comment="已标事件数")

    dataset = relationship("DatasetModel", back_populates="time_series")

    __table_args__ = (
        Index("ix_annotation_timeseries_dataset_status", "dataset_id", "status"),
    )
