from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import MappedBase, ModelMixin, UserMixin


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


class EdgeEventModel(ModelMixin, MappedBase):
    """边缘事件（v2 归一化后落库；只落有检测的事件）。"""

    __tablename__ = "video_edge_events"
    __table_args__ = (
        Index("ix_edge_event_camera_id_id", "camera_id", "id"),
        Index("ix_edge_event_algo_id", "algorithm_type", "id"),
        Index("ix_edge_event_matched_id", "matched", "id"),
        {"comment": "边缘事件表"},
    )

    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="Agent 事件 UUID")
    edge_code: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="边缘设备码")
    camera_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="相机")
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="布控任务")
    algorithm_type: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="场景码")
    ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="事件时间")
    objects: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="v2 对象数组")
    detections: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="兼容检测数组")
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True, comment="推理耗时(ms)")
    snapshot_ref: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="快照引用")
    matched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="是否命中规则")
    matched_rule_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="命中规则")
    matched_leaves: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="命中叶子解释")
