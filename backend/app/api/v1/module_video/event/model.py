from typing import Optional

from sqlalchemy import Integer, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class EventLinkageModel(ModelMixin, UserMixin):
    __tablename__ = "video_event_linkages"
    __table_args__ = ({'comment': '事件联动表'})

    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="联动名称")
    trigger_event: Mapped[str] = mapped_column(String(32), nullable=False, comment="触发事件: ALARM/MOTION/OFFLINE/...")
    trigger_camera_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, comment="触发摄像机ID列表")
    action_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="动作类型: RECORD/ALERT/PTZ/PUSH")
    action_params: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, comment="动作参数")
    status: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="描述")
