
from pydantic import BaseModel, Field

from app.core.base_schema import BaseSchema, CommonSchema
from app.core.validator import DateTimeStr


class RecordPlanCreateSchema(BaseModel):
    camera_id: int = Field(..., description="摄像机ID")
    plan_type: str = Field(default="CONTINUOUS", description="计划类型")
    schedule_json: dict | None = Field(default=None, description="时间段配置")
    pre_record_sec: int = Field(default=5, description="预录秒数")
    post_record_sec: int = Field(default=5, description="延录秒数")
    storage_days: int = Field(default=30, description="存储天数")
    stream_type: str = Field(default="MAIN", description="录制码流")
    status: bool = Field(default=True, description="是否启用")
    description: str | None = Field(default=None, max_length=255, description="备注")


class RecordPlanUpdateSchema(RecordPlanCreateSchema):
    camera_id: int | None = Field(default=None, description="摄像机ID")


class RecordPlanOutSchema(BaseSchema):
    camera_id: int
    plan_type: str
    schedule_json: dict | None = None
    pre_record_sec: int = 5
    post_record_sec: int = 5
    storage_days: int = 30
    stream_type: str = "MAIN"
    status: bool = True
    camera: CommonSchema | None = None


class RecordFileOutSchema(BaseSchema):
    camera_id: int
    stream_id: str | None = None
    file_path: str
    file_size: int | None = None
    duration: int | None = None
    start_time: DateTimeStr | None = None
    end_time: DateTimeStr | None = None
    record_type: str = "CONTINUOUS"
    format: str = "mp4"
    status: str = "COMPLETED"
    camera: CommonSchema | None = None


class RecordExecutionLogOutSchema(BaseSchema):
    plan_id: int
    camera_id: int
    stream_id: str | None = None
    trigger_type: str = "SCHEDULED"
    start_time: DateTimeStr | None = None
    end_time: DateTimeStr | None = None
    duration: int | None = None
    status: str = "RECORDING"
    error_msg: str | None = None
    file_count: int = 0
    camera: CommonSchema | None = None
