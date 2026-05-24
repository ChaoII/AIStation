
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class LayoutModel(ModelMixin, UserMixin):
    __tablename__ = "video_layouts"
    __table_args__ = ({'comment': '布局方案表'})

    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="布局名称")
    grid_type: Mapped[str] = mapped_column(String(8), default="4", comment="布局类型: 1/4/6/8/9/16")
    layout_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="窗口配置(JSON)")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="用户ID")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否默认")
