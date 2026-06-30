from pydantic import BaseModel, Field

from app.core.base_schema import BaseSchema, CommonSchema
from app.core.validator import DateTimeStr


class CameraCreateSchema(BaseModel):
    name: str = Field(..., max_length=128, description="摄像机名称")
    device_type: str = Field(default="IP_CAMERA", description="设备类型")
    stream_type: str = Field(default="MAIN", description="码流类型")

    rtsp_url_main: str | None = Field(default=None, description="主码流RTSP")
    rtsp_url_sub: str | None = Field(default=None, description="子码流RTSP")
    onvif_address: str | None = Field(default=None, description="ONVIF地址")
    onvif_port: int = Field(default=80, description="ONVIF端口")

    gb28181_device_id: str | None = Field(default=None, description="GB28181设备ID")
    gb28181_channel_id: str | None = Field(default=None, description="GB28181通道ID")

    username: str | None = Field(default=None, max_length=64, description="用户名")
    password: str | None = Field(default=None, max_length=128, description="密码")

    group_id: int | None = Field(default=None, description="分组ID")
    location: str | None = Field(default=None, max_length=256, description="安装位置")
    latitude: float | None = Field(default=None, description="纬度")
    longitude: float | None = Field(default=None, description="经度")

    brand: str | None = Field(default=None, max_length=64, description="品牌")
    model_name: str | None = Field(default=None, max_length=64, description="型号")
    firmware: str | None = Field(default=None, max_length=64, description="固件")

    extra: dict | None = Field(default=None, description="扩展属性")
    sort_order: int = Field(default=0, description="排序")
    description: str | None = Field(default=None, max_length=255, description="备注")


class CameraUpdateSchema(CameraCreateSchema):
    name: str | None = Field(default=None, max_length=128, description="摄像机名称")


class CameraOutSchema(BaseSchema):
    name: str = Field(description="摄像机名称")
    device_type: str = Field(description="设备类型")
    stream_type: str = Field(description="码流类型")

    rtsp_url_main: str | None = None
    rtsp_url_sub: str | None = None
    onvif_address: str | None = None
    onvif_port: int = 80

    gb28181_device_id: str | None = None
    gb28181_channel_id: str | None = None

    status: str = "OFFLINE"
    stream_status: str | None = None
    stream_id: str | None = None
    stream_source: str | None = None
    reachable: bool | None = None
    last_online_time: DateTimeStr | None = None

    group_id: int | None = None
    group: CommonSchema | None = None

    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    brand: str | None = None
    model_name: str | None = None
    firmware: str | None = None

    extra: dict | None = None
    sort_order: int = 0

    play_urls: dict | None = None


class CameraGroupCreateSchema(BaseModel):
    name: str = Field(..., max_length=64, description="分组名称")
    parent_id: int | None = Field(default=None, description="上级分组ID")
    sort_order: int = Field(default=0, description="排序")
    status: bool = Field(default=True, description="是否启用")
    description: str | None = Field(default=None, max_length=255, description="备注")


class CameraGroupUpdateSchema(CameraGroupCreateSchema):
    name: str | None = Field(default=None, max_length=64, description="分组名称")


class CameraGroupOutSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    parent_id: int | None = None
    sort_order: int = 0
    status: bool = True
    description: str | None = None
    created_at: DateTimeStr | None = None
    updated_at: DateTimeStr | None = None
