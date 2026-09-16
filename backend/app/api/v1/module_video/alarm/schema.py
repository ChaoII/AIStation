
from pydantic import BaseModel, Field, computed_field

from app.core.base_schema import BaseSchema, CommonSchema
from app.core.validator import DateTimeStr


class AlarmRuleCreateSchema(BaseModel):
    name: str = Field(..., max_length=128, description="规则名称")
    camera_id: int | None = Field(default=None, description="摄像机ID")
    group_id: int | None = Field(default=None, description="摄像机组ID（与 camera_id 恰有其一）")
    alarm_type: str = Field(..., description="告警类型")
    algorithm_task_id: int | None = Field(default=None, description="算法任务ID")
    severity: str = Field(default="WARNING", description="严重级别")
    detect_region: dict | None = Field(default=None, description="检测区域")
    sensitivity: int = Field(default=50, ge=1, le=100, description="灵敏度")
    interval_seconds: int = Field(default=30, description="告警间隔")
    notify_channels: list | None = Field(default=None, description="通知方式")
    conditions: dict | None = Field(default=None, description="规则条件树")
    params: dict = Field(default_factory=dict, description="场景参数原值")
    schedule_json: dict | None = Field(default=None, description="生效时间段")
    rollout: dict = Field(default_factory=dict, description="灰度配置: {percent, whitelist, blacklist}")
    status: bool = Field(default=True, description="是否启用")
    description: str | None = Field(default=None, max_length=255, description="备注")


class AlarmRuleUpdateSchema(AlarmRuleCreateSchema):
    name: str | None = Field(default=None, max_length=128)
    camera_id: int | None = Field(default=None)
    group_id: int | None = Field(default=None)


class AlarmRuleOutSchema(BaseSchema):
    name: str
    camera_id: int | None = None
    group_id: int | None = None
    alarm_type: str
    algorithm_task_id: int | None = None
    severity: str = "WARNING"
    detect_region: dict | None = None
    sensitivity: int = 50
    interval_seconds: int = 30
    notify_channels: list | None = None
    conditions: dict | None = None
    params: dict = Field(default_factory=dict, description="场景参数原值")
    schedule_json: dict | None = None
    rollout: dict = Field(default_factory=dict, description="灰度配置: {percent, whitelist, blacklist}")
    status: bool = True
    camera: CommonSchema | None = None


class AlarmRecordConfirmSchema(BaseModel):
    status: str = Field(..., description="状态: CONFIRMED/IGNORED/FALSE_ALARM")


class AlarmRecordOutSchema(BaseSchema):
    camera_id: int
    rule_id: int | None = None
    alarm_type: str
    severity: str = "WARNING"
    snapshot_path: str | None = None
    video_clip_path: str | None = None
    alarm_time: DateTimeStr | None = None
    confirm_time: DateTimeStr | None = None
    confirm_user: str | None = None
    status: str = "PENDING"
    ai_result: dict | None = None
    camera: CommonSchema | None = None
    rule: CommonSchema | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def snapshot_url(self) -> str | None:
        """快照可访问 URL（按本地文件 / 对象存储归一化）。"""
        from app.api.v1.module_video.inference.snapshot import resolve_snapshot_url

        return resolve_snapshot_url(self.snapshot_path)
