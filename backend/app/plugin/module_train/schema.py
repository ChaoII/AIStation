from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class TrainModelCreateSchema(BaseModel):
    name: str = Field(max_length=128)
    framework: str
    annotation_dataset_id: int | None = None
    export_format: str | None = None


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


class DatasetExportSchema(BaseModel):
    dataset_id: int
    annotation_task_id: int | None = None
    format: str = "ultralytics"
