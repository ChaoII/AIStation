from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AnnotationSaveSchema(BaseModel):
    task_id: int
    image_id: int
    annotation_data: list[dict]


class AnnotationOutSchema(BaseModel):
    id: int
    task_id: int
    image_id: int
    annotation_data: list
    version: int
    created_id: int | None
    created_time: datetime | None
    updated_time: datetime | None