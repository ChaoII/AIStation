from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin

from .model import TrainFramework


class TrainScheduleModel(ModelMixin, UserMixin):
    __tablename__ = "train_schedules"

    name: Mapped[str] = mapped_column(String(128), comment="计划名称")
    dataset_id: Mapped[int] = mapped_column(ForeignKey("annotation_dataset.id"), comment="数据集ID")
    annotation_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="标注任务ID")
    # 默认值曾是 "ultralytics"，是历史脏数据（37 条任务里不少 framework 由此而来）
    # 的根源之一。Ultralytics 已退场，定时训练只支持自研平台。
    # 该列在 PG 里**没有 server_default**（实测 column_default 为 NULL），所以新建行
    # 会拿到下面的 Python 侧默认值；但创建/更新定时计划的 service 仍必须显式赋值并
    # 挡退场框架（见 schedule_service.py），不能依赖默认值兜底。
    #
    # ⚠️ 映射必须与库里一致：该列在 PG 里是**枚举类型 `trainframework`**（与
    # `TrainTask`/`TrainModel` 等同款），此处若写成 `String(16)`，插入时会报
    # `column "framework" is of type trainframework but expression is of type character varying`
    # ——「定时训练计划创建不了」的既有 bug（2026-10-18 由 e2e 暴露）。写入方须传
    # `TrainFramework` 成员（见 `framework_utils.framework_value`）。
    framework: Mapped[TrainFramework] = mapped_column(
        SAEnum(TrainFramework), default=TrainFramework.TORKILN, comment="训练框架"
    )
    hyperparams: Mapped[dict] = mapped_column(JSONB, default=dict, comment="超参数")
    trigger: Mapped[str] = mapped_column(
        String(16), nullable=False, default="cron", server_default="cron",
        comment="触发类型 cron/interval/date/now",
    )
    trigger_args: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None, comment="触发参数（cron 5 段 / interval JSON / date 时间）"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="上次执行时间")
    last_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="上次触发的训练任务ID")
