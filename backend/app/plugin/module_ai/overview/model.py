from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin


class AiCallLogModel(ModelMixin):
    """AI 调用日志：模型/用途/耗时/结果，用于控制台观测。"""

    __tablename__ = "ai_call_logs"
    __table_args__ = ({"comment": "AI 调用日志表"},)

    model_name: Mapped[str] = mapped_column(String(128), default="", comment="模型名")
    usage: Mapped[str] = mapped_column(String(32), default="chat", comment="用途")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, comment="耗时(ms)")
    result: Mapped[str] = mapped_column(String(16), default="success", comment="success/error")
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")
    app_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="应用ID")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True, comment="调用用户ID")
