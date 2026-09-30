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
    # 默认值曾是 "ultralytics"，是历史脏数据（37 条任务里不少 framework 由此而来）
    # 的根源之一。Ultralytics 已退场，定时训练只支持自研平台。
    # ⚠️ 该列在 PG 里的 server_default 仍是 'ultralytics'（见 alembic 迁移），对既有表
    # 依然生效——新插入的行若不显式给 framework 会拿到退场框架。因此创建/更新定时
    # 计划的 service 必须显式赋值并挡退场框架（见 schedule_service.py）。
    framework: Mapped[str] = mapped_column(String(16), default="torchkiln", comment="训练框架")
    hyperparams: Mapped[dict] = mapped_column(JSONB, default=dict, comment="超参数")
    cron_expr: Mapped[str] = mapped_column(String(64), comment="Cron 表达式, 如 0 2 * * 0 (每周日凌晨2点)")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="上次执行时间")
    last_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="上次触发的训练任务ID")
