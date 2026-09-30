import enum
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy import Enum as SAEnum
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
    """训练框架。

    ⚠️ ``ULTRALYTICS`` / ``PADDLEX`` **已退场**：执行通路（训练、评估、预测、部署、
    格式转换导出）全部移除，新建入口由 ``retired.ensure_active()`` 拒绝。但这两个
    成员**必须保留**——库里还有 92 个 ULTRALYTICS 模型与 37 条历史训练任务，
    SQLAlchemy 的 ``SAEnum`` 按成员名反序列化，删掉成员会让读那些行直接报
    ``invalid input value for enum``，整个模型列表页都打不开。
    「代码退场」不等于「数据消失」：枚举值留着让历史可读，新建时才由 service 层拒绝。

    同理，PG 枚举 ``trainframework`` 里的 ``PYTORCH_OCR_DET`` / ``PYTORCH_OCR_REC``
    也早已没有对应成员（本项目既有做法），由 init_app 兜底补齐。
    """
    ULTRALYTICS = "ultralytics"
    PADDLEX = "paddlex"
    # 自研训练平台（D:\TorchKiln）以每任务一容器形态接入：超参点分键直通、指标走
    # metrics.jsonl 契约，**不再解析容器控制台日志**。
    # ⚠️ PG 枚举 trainframework 需同步 ALTER TYPE ADD VALUE 'TORKILN'
    #    （见 app/scripts/init_app.py 的 _ensure_trainframework_enum_values）
    TORKILN = "torchkiln"


class TrainModelRepo(ModelMixin, UserMixin):
    """模型仓库：以模型名称聚合的一组版本。"""
    __tablename__ = "train_model_repos"
    name: Mapped[str] = mapped_column(String(128), unique=True, comment="模型名称（仓库唯一）")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), comment="训练框架")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    latest_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最新版本ID")
    annotation_dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="来源数据集ID")
    status: Mapped[str] = mapped_column(String(16), default="draft", comment="draft/released/archived")


class TrainModel(ModelMixin, UserMixin):
    __tablename__ = "train_models"
    repo_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="所属仓库ID")
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
    # ⚠️ 字段名有误导：这里存的是**模型版本行 id**（train_models.id），不是仓库 id。
    #    历史遗留（见 test_retired_frameworks 之外的既有数据）。
    # nullable：2026-07 数据事故删掉了一批模型行，留下指向已删 id 的悬空引用。
    #   NOT NULL 时结构上无法表达"引用的模型已删除"这一合法状态——既不能修复，
    #   也不能如实记录。改为可空后，悬空引用可被置空（迁移见 c4d5e6f7a8b9）。
    model_repo_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="模型版本ID（字段名沿用历史，实为版本行 id）")
    model_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="具体模型版本ID")
    eval_dataset_id: Mapped[int] = mapped_column(Integer, comment="评估数据集ID")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), default=TrainFramework.TORKILN, comment="框架（ULTRALYTICS/PADDLEX 已退场，仅历史数据保留）")
    hyperparams: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="评估参数")
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="评估指标")
    status: Mapped[TrainStatus] = mapped_column(SAEnum(TrainStatus), default=TrainStatus.PENDING, comment="状态")
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="进度0-100")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")
    log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="评估日志")
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误日志")
    metrics_log: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None, comment="每轮评估指标")
    best_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None, comment="最优指标")
    last_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None, comment="最终指标")


class TrainPredict(ModelMixin, UserMixin):
    __tablename__ = "train_predicts"
    # 同 TrainEval.model_repo_id：存的是模型版本行 id，且允许为 NULL
    # （模型被删后需能如实记录"预测目标已不存在"，见迁移 c4d5e6f7a8b9）。
    model_repo_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="模型版本ID（字段名沿用历史，实为版本行 id）")
    model_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="模型版本ID（模型被删后置空）")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), default=TrainFramework.TORKILN, comment="框架（ULTRALYTICS/PADDLEX 已退场，仅历史数据保留）")
    source_type: Mapped[str] = mapped_column(String(16), comment="图片来源 dataset/upload")
    source_dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="源数据集ID")
    source_images: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="上传图片原始URL列表")
    result_images: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="结果图片URL列表")
    result_zip_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="结果ZIP在RustFS的路径")
    hyperparams: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="预测参数")
    status: Mapped[TrainStatus] = mapped_column(SAEnum(TrainStatus), default=TrainStatus.PENDING, comment="状态")
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="进度0-100")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")
    log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="预测日志")
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误日志")


class TrainDeploy(ModelMixin, UserMixin):
    __tablename__ = "train_deploys"
    name: Mapped[str] = mapped_column(String(128), comment="部署名称")
    model_id: Mapped[int] = mapped_column(Integer, comment="模型ID")
    model_name: Mapped[str] = mapped_column(String(128), comment="模型名称")
    model_version: Mapped[str] = mapped_column(String(32), comment="模型版本")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), default=TrainFramework.TORKILN, comment="框架（ULTRALYTICS/PADDLEX 已退场，仅历史数据保留）")
    device: Mapped[str] = mapped_column(String(16), default="0", comment="GPU设备ID或cpu")
    host_port: Mapped[int] = mapped_column(Integer, comment="宿主机端口")
    container_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="Docker容器ID")
    status: Mapped[str] = mapped_column(String(16), default="pending", comment="deploying/running/stopped/failed")
    api_url: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="API地址")
    api_key: Mapped[str] = mapped_column(String(64), comment="API密钥")
    docker_image: Mapped[str] = mapped_column(String(256), default="torchkiln:0.1.0", comment="Docker镜像")
    hyperparams: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="推理参数")
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误日志")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")
