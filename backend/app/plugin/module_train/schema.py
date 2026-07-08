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
    log: str | None
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
