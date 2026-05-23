from datetime import datetime
from typing import Optional, List

from sqlalchemy import Boolean, Integer, String, DateTime, Text, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_model import MappedBase, ModelMixin, UserMixin


class CameraGroupModel(MappedBase):
    __tablename__ = "video_camera_groups"
    __table_args__ = ({'comment': '摄像机分组表'})

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="分组名称")
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None, comment="上级分组ID")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    status: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="备注")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=datetime.now)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=datetime.now, onupdate=datetime.now)


class CameraModel(ModelMixin, UserMixin):
    __tablename__ = "video_cameras"
    __table_args__ = ({'comment': '摄像机表'})
    __loader_options__ = ["group", "creator"]

    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="摄像机名称")
    device_type: Mapped[str] = mapped_column(String(32), default="IP_CAMERA", comment="设备类型: IP_CAMERA/GB28181/NVR/ONVIF")
    stream_type: Mapped[str] = mapped_column(String(16), default="MAIN", comment="码流类型: MAIN/SUB")

    rtsp_url_main: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="主码流RTSP地址")
    rtsp_url_sub: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="子码流RTSP地址")
    onvif_address: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, comment="ONVIF地址")
    onvif_port: Mapped[int] = mapped_column(Integer, default=80, comment="ONVIF端口")

    gb28181_device_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="GB28181设备ID")
    gb28181_channel_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="GB28181通道ID")

    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="登录用户名")
    password: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="登录密码")

    status: Mapped[str] = mapped_column(String(16), default="OFFLINE", comment="状态: ONLINE/OFFLINE/ERROR")
    stream_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, comment="流状态: PUSHING/IDLE/ERROR")
    stream_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="ZLM stream_id")
    last_online_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最后在线时间")

    group_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("video_camera_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    group: Mapped[Optional["CameraGroupModel"]] = relationship(lazy="selectin")

    location: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, comment="安装位置")
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="纬度")
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="经度")

    brand: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="品牌")
    model_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="型号")
    firmware: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="固件版本")

    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=dict, comment="扩展属性(JSONB)")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
