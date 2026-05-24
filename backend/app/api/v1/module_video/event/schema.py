
from pydantic import BaseModel, Field

from app.core.base_schema import BaseSchema


class EventCreateSchema(BaseModel):
    name: str = Field(..., max_length=128, description="联动名称")
    trigger_event: str = Field(..., max_length=32, description="触发事件")
    trigger_camera_ids: list | None = Field(default=None, description="触发摄像机ID列表")
    action_type: str = Field(..., max_length=32, description="动作类型")
    action_params: dict | None = Field(default=None, description="动作参数")
    status: bool = Field(default=True, description="是否启用")
    description: str | None = Field(default=None, max_length=255, description="描述")


class EventUpdateSchema(EventCreateSchema):
    name: str | None = Field(default=None, max_length=128, description="联动名称")
    trigger_event: str | None = Field(default=None, max_length=32, description="触发事件")
    action_type: str | None = Field(default=None, max_length=32, description="动作类型")


class EventOutSchema(BaseSchema):
    name: str
    trigger_event: str
    trigger_camera_ids: list | None = None
    action_type: str
    action_params: dict | None = None
    status: bool = True
