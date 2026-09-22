from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field


class AxisAlignedBoxSchema(BaseModel):
    """2D 目标检测矩形框（归一化 [0,1]，结构同 detection 导出）。"""

    id: str | None = None
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
    task_id: int
    video_id: int
    frame_index: int = Field(ge=0, description="帧序号")
    annotations: list[AxisAlignedBoxSchema] = Field(default_factory=list)


class TextAnnotationSaveSchema(BaseModel):
    """文本 NER 文档标注保存请求。

    ``annotations`` 为实体与关系混合列表，逐项结构在后端 service 层
    结合任务 classes 与文档字符数做实体/关系/重叠校验。
    """

    task_id: int
    document_id: int
    annotations: list[dict] = Field(default_factory=list)


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
