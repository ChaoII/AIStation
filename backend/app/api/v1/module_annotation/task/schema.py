from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.module_annotation.dataset.model import AnnotationType


class TaskCreateSchema(BaseModel):
    dataset_id: int
    name: str = Field(max_length=128)
    task_type: AnnotationType
    assignees: list[int] = Field(default_factory=list)
    classes: list[dict] = Field(default_factory=list)


class TaskUpdateSchema(BaseModel):
    name: str | None = Field(None, max_length=128)
    assignees: list[int] | None = None
    classes: list[dict] | None = None


class TaskOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    name: str
    task_type: AnnotationType
    status: str
    assignees: list
    classes: Any
    progress: int
    created_id: int | None
    created_time: datetime | None
    updated_time: datetime | None
    completed_at: datetime | None
