from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class EdgeDeviceModel(ModelMixin, UserMixin):
    """边缘设备表：登记边缘节点能力、控制面地址与实时心跳。"""

    __tablename__ = "video_edge_devices"
    __table_args__ = ({'comment': '边缘设备表'})

    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="设备名称")
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="设备唯一编码")
    control_url: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="Agent 控制面基址")
    secret: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="控制面鉴权密钥")

    capabilities: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="能力清单（模型族/后端/最大路数/硬件等）")
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="实时指标（CPU/GPU/显存/在跑路数）")

    status: Mapped[str] = mapped_column(String(16), default="offline", comment="状态: online/offline/busy/error")
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最后心跳时间")
