from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .model import AnnotationType


class DatasetCreateSchema(BaseModel):
    name: str = Field(max_length=128)
    description: str | None = None
    annotation_type: AnnotationType


class DatasetUpdateSchema(BaseModel):
    name: str | None = Field(None, max_length=128)
    description: str | None = None


class DatasetOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    annotation_type: AnnotationType
    image_count: int
    annotated_count: int
    task_count: int = 0
    status: str
    created_id: int | None
    created_time: datetime | None
    updated_time: datetime | None


class ImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    filename: str
    object_key: str
    width: int
    height: int
    status: str
    locked_by: int | None
    annotation_count: int
    created_time: datetime | None
