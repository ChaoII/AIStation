
from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AnnotationRecordModel(ModelMixin, UserMixin):
    __tablename__ = "annotation_record"

    task_id: Mapped[int] = mapped_column(ForeignKey("annotation_task.id"), comment="任务ID")
    image_id: Mapped[int] = mapped_column(ForeignKey("annotation_image.id"), comment="图片ID")
    annotation_data: Mapped[dict] = mapped_column(JSONB, comment="标注 JSON 数据")
    version: Mapped[int] = mapped_column(Integer, default=1, comment="版本号")

    __mapper_args__ = {"eager_defaults": True}
