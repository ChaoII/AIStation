from typing import Optional
from pydantic import BaseModel, Field

from app.core.base_schema import BaseSchema


class AlarmRuleCreateSchema(BaseModel):
    name: str = Field(..., max_length=128, description="规则名称")
    camera_id: int = Field(..., description="摄像机ID")
    alarm_type: str = Field(..., description="告警类型")
    algorithm_task_id: Optional[int] = Field(default=None, description="算法任务ID")
    severity: str = Field(default="WARNING", description="严重级别")
    detect_region: Optional[dict] = Field(default=None, description="检测区域")
    sensitivity: int = Field(default=50, ge=1, le=100, description="灵敏度")
    interval_seconds: int = Field(default=30, description="告警间隔")
    notify_channels: Optional[list] = Field(default=None, description="通知方式")
    schedule_json: Optional[dict] = Field(default=None, description="生效时间段")
    status: bool = Field(default=True, description="是否启用")
    description: Optional[str] = Field(default=None, max_length=255, description="备注")


class AlarmRuleUpdateSchema(AlarmRuleCreateSchema):
    name: Optional[str] = Field(default=None, max_length=128)
    camera_id: Optional[int] = Field(default=None)


class AlarmRuleOutSchema(BaseSchema):
    name: str
    camera_id: int
    alarm_type: str
    algorithm_task_id: Optional[int] = None
    severity: str = "WARNING"
    detect_region: Optional[dict] = None
    sensitivity: int = 50
    interval_seconds: int = 30
    notify_channels: Optional[list] = None
    schedule_json: Optional[dict] = None
    status: bool = True
    camera: Optional[dict] = None


class AlarmRecordConfirmSchema(BaseModel):
    status: str = Field(..., description="状态: CONFIRMED/IGNORED/FALSE_ALARM")


class AlarmRecordOutSchema(BaseSchema):
    camera_id: int
    rule_id: Optional[int] = None
    alarm_type: str
    severity: str = "WARNING"
    snapshot_path: Optional[str] = None
    video_clip_path: Optional[str] = None
    alarm_time: Optional[str] = None
    confirm_time: Optional[str] = None
    confirm_user: Optional[str] = None
    status: str = "PENDING"
    ai_result: Optional[dict] = None
    camera: Optional[dict] = None
    rule: Optional[dict] = None
