from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.config.setting import settings
from app.core.base_schema import BaseSchema
from app.core.validator import DateTimeStr
from app.utils.url_guard import UnsafeUrlError, validate_outbound_url


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

    @field_validator("control_url")
    @classmethod
    def _validate_control_url(cls, value: str | None) -> str | None:
        """拒绝指向非 http(s)/元数据/链路本地的控制面地址（审计 #12）。"""
        if value:
            try:
                validate_outbound_url(
                    value,
                    block_private=settings.EDGE_CONTROL_URL_BLOCK_PRIVATE,
                    allowed_hosts=set(settings.EDGE_CONTROL_URL_ALLOWED_HOSTS) or None,
                )
            except UnsafeUrlError as e:
                raise ValueError(f"control_url 不安全：{e}") from e
        return value


class EdgeDeviceUpdateSchema(EdgeDeviceCreateSchema):
    name: str | None = Field(default=None, max_length=128, description="设备名称")
    code: str | None = Field(default=None, max_length=64, description="设备唯一编码")
    status: str | None = Field(default=None, max_length=16, description="状态")


class EdgeDeviceOutSchema(BaseSchema):
    # 出参脱敏：secret 属控制面鉴权密钥，仅保留在 Create/Update 入参中，禁止回显
    name: str
    code: str
    control_url: str | None = None
    capabilities: dict | None = None
    metrics: dict | None = None
    status: str = "offline"
    last_heartbeat: DateTimeStr | None = None
