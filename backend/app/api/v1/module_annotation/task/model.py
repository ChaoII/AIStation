import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.api.v1.module_annotation.dataset.model import AnnotationType
from app.core.base_model import ModelMixin, UserMixin


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class AnnotationTaskModel(ModelMixin, UserMixin):
    __tablename__ = "annotation_task"

    dataset_id: Mapped[int] = mapped_column(ForeignKey("annotation_dataset.id"), comment="数据集ID")
    name: Mapped[str] = mapped_column(String(128), comment="任务名称")
    task_type: Mapped[AnnotationType] = mapped_column(Enum(AnnotationType), comment="标注类型")
    status: Mapped[str] = mapped_column(String(16), default="pending", comment="状态")
    assignees: Mapped[list] = mapped_column(JSONB, default=list, comment="协作者ID列表")
    classes: Mapped[dict] = mapped_column(JSONB, default=dict, comment="类别定义 [{id, name, color, keypoint_names?}]")
    classification_mode: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="分类模式: single/multi")
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="完成百分比")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")

    dataset = relationship("DatasetModel", back_populates="tasks")

    __mapper_args__ = {"eager_defaults": True}
