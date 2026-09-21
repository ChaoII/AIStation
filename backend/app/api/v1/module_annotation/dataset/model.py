import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import ModelMixin, UserMixin


class AnnotationType(str, enum.Enum):
    DETECTION = "detection"
    ROTATED_DETECTION = "rotated_detection"
    SEGMENTATION = "segmentation"
    SEMANTIC_SEGMENTATION = "semantic_segmentation"
    POLYLINE = "polyline"
    PANOPTIC_SEGMENTATION = "panoptic_segmentation"
    KEYPOINT = "keypoint"
    OCR = "ocr"
    CLASSIFICATION = "classification"


class DatasetStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class DatasetModel(ModelMixin, UserMixin):
    __tablename__ = "annotation_dataset"

    name: Mapped[str] = mapped_column(String(128), comment="数据集名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    image_count: Mapped[int] = mapped_column(Integer, default=0, comment="图片总数")
    annotated_count: Mapped[int] = mapped_column(Integer, default=0, comment="已标注图片数")

    images = relationship("AnnotationImageModel", back_populates="dataset", lazy="dynamic")
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
