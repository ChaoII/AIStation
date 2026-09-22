from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field


class AxisAlignedBoxSchema(BaseModel):
    """2D 目标检测矩形框（归一化 [0,1]，结构同 detection 导出）。"""

    id: str
    type: str = "AxisAlignedBox"
    class_id: int
    x1: Annotated[float, Field(ge=0.0, le=1.0)]
    y1: Annotated[float, Field(ge=0.0, le=1.0)]
    x2: Annotated[float, Field(ge=0.0, le=1.0)]
    y2: Annotated[float, Field(ge=0.0, le=1.0)]


class AnnotationSaveSchema(BaseModel):
    task_id: int
    image_id: int
    annotation_data: list[dict]


class VideoAnnotationSaveSchema(BaseModel):
    video_id: int
    frame_index: int = Field(ge=0, description="帧序号")
    annotations: list[AxisAlignedBoxSchema] = Field(default_factory=list)


class AnnotationRollbackSchema(BaseModel):
    task_id: int
    version: int


class AnnotationOutSchema(BaseModel):
    id: int
    task_id: int
    image_id: int
    annotation_data: list
    version: int
    created_id: int | None
    created_time: datetime | None
    updated_time: datetime | None
