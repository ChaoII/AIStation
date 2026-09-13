from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiPromptModel(ModelMixin, UserMixin):
    """提示词模板：有序块（系统/上下文/指令/示例/输出）+ 变量列表。"""

    __tablename__ = "ai_prompts"
    __table_args__ = ({"comment": "AI 提示词模板表"},)

    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment="名称")
    category: Mapped[str] = mapped_column(String(32), default="", comment="分类")
    blocks: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="有序提示词块 [{type,content}]"
    )
    variables: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="变量名列表"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, comment="版本号")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
