from datetime import datetime

from pydantic import BaseModel, Field

from app.core.base_schema import BaseSchema
from app.core.validator import DateTimeStr


class EdgeDeviceCreateSchema(BaseModel):
    name: str = Field(..., max_length=128, description="设备名称")
    code: str = Field(..., max_length=64, description="设备唯一编码")
    control_url: str | None = Field(default=None, max_length=512, description="Agent 控制面基址")
    secret: str | None = Field(default=None, max_length=128, description="控制面鉴权密钥")
    capabilities: dict | None = Field(default=None, description="能力清单")
    metrics: dict | None = Field(default=None, description="实时指标")
    status: str = Field(default="offline", max_length=16, description="状态: online/offline/busy/error")
    last_heartbeat: datetime | None = Field(default=None, description="最后心跳时间")
    description: str | None = Field(default=None, max_length=255, description="描述")


class EdgeDeviceUpdateSchema(EdgeDeviceCreateSchema):
    name: str | None = Field(default=None, max_length=128, description="设备名称")
    code: str | None = Field(default=None, max_length=64, description="设备唯一编码")
    status: str | None = Field(default=None, max_length=16, description="状态")


class EdgeDeviceOutSchema(BaseSchema):
    name: str
    code: str
    control_url: str | None = None
    secret: str | None = None
    capabilities: dict | None = None
    metrics: dict | None = None
    status: str = "offline"
    last_heartbeat: DateTimeStr | None = None
