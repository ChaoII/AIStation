from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin


class AiSessionModel(ModelMixin):
    """AI 会话：按应用/用户分组的对话，记录消息数量。"""

    __tablename__ = "ai_sessions"
    __table_args__ = ({"comment": "AI 会话表"},)

    app_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True, comment="应用ID（空为通用助手）"
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True, comment="所属用户ID"
    )
    title: Mapped[str] = mapped_column(String(255), default="", comment="标题")
    message_count: Mapped[int] = mapped_column(Integer, default=0, comment="消息数量")


class AiMessageModel(ModelMixin):
    """AI 会话消息：存储 AI SDK UI Message 的 parts。"""

    __tablename__ = "ai_messages"
    __table_args__ = ({"comment": "AI 会话消息表"},)

    session_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="会话ID"
    )
    app_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="应用ID")
    role: Mapped[str] = mapped_column(String(16), default="user", comment="角色 user/assistant")
    parts: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="消息 parts [{type,text}]"
    )
