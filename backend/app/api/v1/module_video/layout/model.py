from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import MappedBase


class LayoutModel(MappedBase):
    __tablename__ = "video_layouts"
    __table_args__ = ({'comment': '布局方案表'})

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="布局名称")
    grid_type: Mapped[str] = mapped_column(String(8), default="4", comment="布局类型: 1/4/6/8/9/16")
    layout_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, comment="窗口配置(JSON)")
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="用户ID")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否默认")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="描述")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=datetime.now)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=datetime.now, onupdate=datetime.now)
