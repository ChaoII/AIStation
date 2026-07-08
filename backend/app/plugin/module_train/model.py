import enum
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.base_model import ModelMixin, UserMixin


class TrainStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrainFramework(str, enum.Enum):
    PADDLEX = "paddlex"
    ULTRALYTICS = "ultralytics"


class TrainModel(ModelMixin, UserMixin):
    __tablename__ = "train_models"
    name: Mapped[str] = mapped_column(String(128), comment="模型名称")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), comment="训练框架")
    version: Mapped[str] = mapped_column(String(32), comment="语义版本号")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="RustFS 存储路径")
    format: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="导出格式 ONNX/Paddle/TorchScript")
    export_format: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="数据集导出格式 YOLO/PaddleX")
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="评估指标")
    annotation_dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="来源数据集ID")
    status: Mapped[str] = mapped_column(String(16), default="draft", comment="draft/released/archived")


class TrainTask(ModelMixin, UserMixin):
    __tablename__ = "train_tasks"
    name: Mapped[str] = mapped_column(String(128), comment="任务名称")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), comment="训练框架")
    dataset_id: Mapped[int] = mapped_column(Integer, comment="数据集ID")
    annotation_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="来源标注任务ID")
    model_repo_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="产出模型ID")
    base_model_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="基础模型ID")
    docker_image: Mapped[str] = mapped_column(String(256), comment="Docker 镜像")
    hyperparams: Mapped[dict] = mapped_column(JSONB, default=dict, comment="超参数")
    status: Mapped[TrainStatus] = mapped_column(SAEnum(TrainStatus), default=TrainStatus.PENDING, comment="状态")
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="进度0-100")
    metrics_log: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None, comment="每轮训练指标")
    best_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None, comment="最优指标")
    last_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None, comment="最终指标")
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误日志")
    cleanup_delay_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="训练完成后延迟N分钟删除容器,空=不自动删除")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")


class TrainEval(ModelMixin, UserMixin):
    __tablename__ = "train_evals"
    model_repo_id: Mapped[int] = mapped_column(Integer, comment="模型仓库ID")
    model_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="具体模型版本ID")
    eval_dataset_id: Mapped[int] = mapped_column(Integer, comment="评估数据集ID")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), default=TrainFramework.ULTRALYTICS, comment="框架")
    hyperparams: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="评估参数")
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="评估指标")
    status: Mapped[TrainStatus] = mapped_column(SAEnum(TrainStatus), default=TrainStatus.PENDING, comment="状态")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")
    log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="评估日志")


class TrainPredict(ModelMixin, UserMixin):
    __tablename__ = "train_predicts"
    model_repo_id: Mapped[int] = mapped_column(Integer, comment="模型仓库ID")
    model_id: Mapped[int] = mapped_column(Integer, comment="模型版本ID")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), default=TrainFramework.ULTRALYTICS, comment="框架")
    source_type: Mapped[str] = mapped_column(String(16), comment="图片来源 dataset/upload")
    source_dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="源数据集ID")
    source_images: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="上传图片原始URL列表")
    result_images: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="结果图片URL列表")
    result_zip_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="结果ZIP在RustFS的路径")
    hyperparams: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="预测参数")
    status: Mapped[TrainStatus] = mapped_column(SAEnum(TrainStatus), default=TrainStatus.PENDING, comment="状态")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")
    log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="预测日志")
