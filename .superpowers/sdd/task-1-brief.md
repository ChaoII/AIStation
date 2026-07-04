# Task 1: Backend Plugin Scaffold + Data Models

**Files:**
- Create: `backend/app/plugin/module_train/plugin.toml`
- Create: `backend/app/plugin/module_train/__init__.py` (empty)
- Create: `backend/app/plugin/module_train/model.py`
- Create: `backend/app/plugin/module_train/schema.py`
- Create: `backend/app/alembic/versions/xxxx_train_models.py`

**Interfaces:**
- Consumes: `ModelMixin`, `UserMixin` from `app.core.base_model`
- Consumes: `async_db_session` from `app.core.database`
- Produces: `TrainModel`, `TrainTask`, `TrainEval` SQLAlchemy models
- Produces: `TrainModelCreateSchema`, `TrainModelOutSchema`, `TrainTaskCreateSchema`, `TrainTaskOutSchema`, `TrainEvalCreateSchema`, `TrainEvalOutSchema` Pydantic schemas

## Steps

### Step 1: Create `plugin.toml`

```toml
name = "train"
title = "模型训练子系统"
tags = ["train", "paddlex", "ultralytics"]
```

### Step 2: Create `__init__.py` (empty, marks directory as Python package)

### Step 3: Create `model.py` with three tables

```python
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
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="评估指标")
    annotation_dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="来源数据集ID")
    status: Mapped[str] = mapped_column(String(16), default="draft", comment="draft/released/archived")


class TrainTask(ModelMixin, UserMixin):
    __tablename__ = "train_tasks"
    name: Mapped[str] = mapped_column(String(128), comment="任务名称")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), comment="训练框架")
    dataset_id: Mapped[int] = mapped_column(Integer, comment="数据集ID")
    model_repo_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="产出模型ID")
    base_model_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="基础模型ID")
    docker_image: Mapped[str] = mapped_column(String(256), comment="Docker 镜像")
    hyperparams: Mapped[dict] = mapped_column(JSONB, default=dict, comment="超参数")
    status: Mapped[TrainStatus] = mapped_column(SAEnum(TrainStatus), default=TrainStatus.PENDING, comment="状态")
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="进度0-100")
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误日志")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")


class TrainEval(ModelMixin, UserMixin):
    __tablename__ = "train_evals"
    model_repo_id: Mapped[int] = mapped_column(Integer, comment="模型版本ID")
    eval_dataset_id: Mapped[int] = mapped_column(Integer, comment="评估数据集ID")
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="评估指标")
    status: Mapped[TrainStatus] = mapped_column(SAEnum(TrainStatus), default=TrainStatus.PENDING, comment="状态")
    log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="评估日志")
```

### Step 4: Create `schema.py`

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class TrainModelCreateSchema(BaseModel):
    name: str = Field(max_length=128)
    framework: str
    annotation_dataset_id: int | None = None


class TrainModelOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    framework: str
    version: str
    storage_path: str | None
    format: str | None
    metrics: dict | None
    status: str
    annotation_dataset_id: int | None
    created_id: int | None
    created_time: datetime | None


class TrainTaskCreateSchema(BaseModel):
    name: str = Field(max_length=128)
    framework: str
    dataset_id: int
    base_model_id: int | None = None
    hyperparams: dict = Field(default_factory=dict)


class TrainTaskOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    framework: str
    dataset_id: int
    model_repo_id: int | None
    docker_image: str
    hyperparams: dict
    status: str
    progress: int
    error_log: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_id: int | None
    created_time: datetime | None


class TrainEvalCreateSchema(BaseModel):
    model_repo_id: int
    eval_dataset_id: int


class TrainEvalOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    model_repo_id: int
    eval_dataset_id: int
    metrics: dict | None
    status: str
    log: str | None
    created_time: datetime | None
```

### Step 5: Generate Alembic migration

Run: `uv run main.py revision --env=dev` then `uv run main.py upgrade --env=dev`

### Reporting

Write results to `.superpowers/sdd/task-1-report.md`. Report must include:
1. Each file created path and its content summary
2. Any issues with migration generation
3. Commit sha
