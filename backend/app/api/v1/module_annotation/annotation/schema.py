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
    track_id: str | None = None


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


class AudioAnnotationSaveSchema(BaseModel):
    """音频事件标注保存请求。

    ``annotations`` 为 ``AudioSegment`` 列表，逐项结构（start/end/label_id）在后端
    service 层结合任务 classes 与音频时长做区间/重叠/越界校验。
    """

    task_id: int
    audio_id: int
    annotations: list[dict] = Field(default_factory=list)


class TimeSeriesSegmentSchema(BaseModel):
    """时间序列事件标注项：时间戳区间 + 事件类别。

    ``start``/``end`` 为该序列时间列的时间戳值（``time_unit`` 决定的单位），
    ``[start, end)`` 半开区间；逐项结构在后端 service 层结合任务 classes 与序列
    时间范围做区间/重叠/越界校验。
    """

    id: str | None = None
    type: str = "TimeSeriesSegment"
    start: float
    end: float
    label_id: int


class TimeSeriesAnnotationsSaveSchema(BaseModel):
    """时间序列事件标注保存请求。

    ``annotations`` 为 ``TimeSeriesSegment`` 列表，逐项结构在后端 service 层结合任务
    classes 与序列时间范围做区间/重叠/越界校验。
    """

    task_id: int
    time_series_id: int
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
