from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DatasetCreateSchema(BaseModel):
    name: str = Field(max_length=128)
    description: str | None = None


class DatasetUpdateSchema(BaseModel):
    name: str | None = Field(None, max_length=128)
    description: str | None = None


class DeleteImagesSchema(BaseModel):
    """删除图片：按 id 或按状态筛选（两者至少一个）。"""

    image_ids: list[int] | None = None
    status: str | None = None


class DatasetOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
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


class TimeSeriesCreateSchema(BaseModel):
    """时间序列上传入参（文件改为 multipart，此处保留元数据字段约定）。"""

    name: str
    time_column: str
    value_columns: list[str]
    time_unit: str


class TimeSeriesOutSchema(BaseModel):
    """时间序列元数据输出（含时间/数值列、行数、时间单位与范围）。"""

    id: int
    dataset_id: int
    name: str
    object_key: str
    time_column: str
    value_columns: list[str]
    row_count: int
    time_unit: str
    start_time: float | None
    end_time: float | None
    size_bytes: int
    status: str
    locked_by: int | None
    annotation_count: int


class TimeSeriesListOutSchema(BaseModel):
    """时间序列列表输出：包裹 items。"""

    items: list[TimeSeriesOutSchema]
