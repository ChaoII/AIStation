from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

from app.core.base_schema import BaseSchema


class CameraCreateSchema(BaseModel):
    name: str = Field(..., max_length=128, description="摄像机名称")
    device_type: str = Field(default="IP_CAMERA", description="设备类型")
    stream_type: str = Field(default="MAIN", description="码流类型")

    rtsp_url_main: Optional[str] = Field(default=None, description="主码流RTSP")
    rtsp_url_sub: Optional[str] = Field(default=None, description="子码流RTSP")
    onvif_address: Optional[str] = Field(default=None, description="ONVIF地址")
    onvif_port: int = Field(default=80, description="ONVIF端口")

    gb28181_device_id: Optional[str] = Field(default=None, description="GB28181设备ID")
    gb28181_channel_id: Optional[str] = Field(default=None, description="GB28181通道ID")

    username: Optional[str] = Field(default=None, max_length=64, description="用户名")
    password: Optional[str] = Field(default=None, max_length=128, description="密码")

    group_id: Optional[int] = Field(default=None, description="分组ID")
    location: Optional[str] = Field(default=None, max_length=256, description="安装位置")
    latitude: Optional[float] = Field(default=None, description="纬度")
    longitude: Optional[float] = Field(default=None, description="经度")

    brand: Optional[str] = Field(default=None, max_length=64, description="品牌")
    model_name: Optional[str] = Field(default=None, max_length=64, description="型号")
    firmware: Optional[str] = Field(default=None, max_length=64, description="固件")

    extra: Optional[dict] = Field(default=None, description="扩展属性")
    sort_order: int = Field(default=0, description="排序")
    description: Optional[str] = Field(default=None, max_length=255, description="备注")


class CameraUpdateSchema(CameraCreateSchema):
    name: Optional[str] = Field(default=None, max_length=128, description="摄像机名称")


class CameraOutSchema(BaseSchema):
    name: str = Field(description="摄像机名称")
    device_type: str = Field(description="设备类型")
    stream_type: str = Field(description="码流类型")

    rtsp_url_main: Optional[str] = None
    rtsp_url_sub: Optional[str] = None
    onvif_address: Optional[str] = None
    onvif_port: int = 80

    gb28181_device_id: Optional[str] = None
    gb28181_channel_id: Optional[str] = None

    status: str = "OFFLINE"
    stream_status: Optional[str] = None
    stream_id: Optional[str] = None
    last_online_time: Optional[str] = None

    group_id: Optional[int] = None
    group: Optional[dict] = None

    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    brand: Optional[str] = None
    model_name: Optional[str] = None
    firmware: Optional[str] = None

    extra: Optional[dict] = None
    sort_order: int = 0

    play_urls: Optional[dict] = None
