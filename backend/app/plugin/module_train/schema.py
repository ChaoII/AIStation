from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TrainModelCreateSchema(BaseModel):
    name: str = Field(max_length=128)
    framework: str
    annotation_dataset_id: int | None = None
    export_format: str | None = None
    description: str | None = None


class TrainModelOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    framework: str
    version: str
    storage_path: str | None
    format: str | None
    export_format: str | None
    metrics: dict | None
    status: str
    annotation_dataset_id: int | None
    created_id: int | None
    created_time: datetime | None


class TrainTaskCreateSchema(BaseModel):
    name: str = Field(max_length=128)
    framework: str
    dataset_id: int
    annotation_task_id: int | None = None
    base_model_id: int | None = None
    hyperparams: dict = Field(default_factory=dict)


class TrainTaskOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    framework: str
    dataset_id: int
    annotation_task_id: int | None
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
    model_id: int | None = None
    eval_dataset_id: int
    hyperparams: dict = Field(default_factory=dict)


class TrainEvalOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    model_repo_id: int
    model_id: int | None
    eval_dataset_id: int
    framework: str
    hyperparams: dict | None
    metrics: dict | None
    status: str
    progress: int
    log: str | None
    error_log: str | None
    metrics_log: list | None
    best_metrics: dict | None
    last_metrics: dict | None
    started_at: datetime | None
    finished_at: datetime | None
    created_id: int | None
    created_time: datetime | None


class TrainPredictCreateSchema(BaseModel):
    model_repo_id: int
    model_id: int
    source_type: str = Field(pattern=r"^(dataset|upload)$")
    source_dataset_id: int | None = None
    source_images: list[str] | None = None
    hyperparams: dict = Field(default_factory=dict)


class TrainPredictOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    model_repo_id: int
    model_id: int
    framework: str
    source_type: str
    source_dataset_id: int | None
    source_images: list | None
    result_images: list | None
    result_zip_path: str | None
    hyperparams: dict | None
    status: str
    progress: int
    started_at: datetime | None
    finished_at: datetime | None
    log: str | None
    created_id: int | None
    created_time: datetime | None


class DatasetExportSchema(BaseModel):
    dataset_id: int
    annotation_task_id: int | None = None
    format: str = "ultralytics"
    ocr_rec: bool = True
    train_ratio: float = 0.8


class TrainScheduleCreateSchema(BaseModel):
    name: str = Field(max_length=128)
    dataset_id: int
    annotation_task_id: int | None = None
    framework: str = "ultralytics"
    hyperparams: dict = {}
    cron_expr: str


class TrainScheduleUpdateSchema(BaseModel):
    name: str | None = None
    dataset_id: int | None = None
    annotation_task_id: int | None = None
    framework: str | None = None
    hyperparams: dict | None = None
    cron_expr: str | None = None
    enabled: bool | None = None


class ModelExportSchema(BaseModel):
    format: str = "onnx"
    imgsz: int = 640
    batch: int = 1
    device: str = "cpu"
    quantize: int | str | None = None
    simplify: bool = True
    opset: int | None = None
    workspace: float | None = None
    nms: bool = False
    end2end: bool | None = None
    dynamic: bool = False
    optimize: bool = False
    keras: bool = False
    data: str | None = None
    fraction: float = 1.0


class ModelUpdateSchema(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None  # draft / released / archived


class TrainDeployCreateSchema(BaseModel):
    model_id: int
    name: str | None = None
    device: str = "0"
    host_port: int | None = None
    hyperparams: dict = Field(default_factory=lambda: {"conf": 0.25, "iou": 0.45, "imgsz": 640})


class TrainDeployOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    model_id: int
    model_name: str
    model_version: str
    framework: str
    device: str
    host_port: int
    container_id: str | None
    status: str
    api_url: str | None
    api_key: str
    docker_image: str
    hyperparams: dict | None
    error_log: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_time: datetime | None
    created_id: int | None
