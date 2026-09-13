from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiReportModel(ModelMixin, UserMixin):
    """AI 生成的报告（Markdown）。"""

    __tablename__ = "ai_reports"
    __table_args__ = ({"comment": "AI 生成报告表"},)

    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="标题")
    content: Mapped[str] = mapped_column(Text, default="", comment="Markdown 内容")
    source: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="来源数据/工具参数"
    )
