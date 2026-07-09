from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class TrainScheduleModel(ModelMixin, UserMixin):
    __tablename__ = "train_schedules"

    name: Mapped[str] = mapped_column(String(128), comment="计划名称")
    dataset_id: Mapped[int] = mapped_column(ForeignKey("annotation_dataset.id"), comment="数据集ID")
    annotation_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="标注任务ID")
    framework: Mapped[str] = mapped_column(String(16), default="ultralytics", comment="训练框架")
    hyperparams: Mapped[dict] = mapped_column(JSONB, default=dict, comment="超参数")
    cron_expr: Mapped[str] = mapped_column(String(64), comment="Cron 表达式, 如 0 2 * * 0 (每周日凌晨2点)")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="上次执行时间")
    last_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="上次触发的训练任务ID")
