from pydantic import BaseModel, Field


class AiSessionCreateSchema(BaseModel):
    """新建会话。"""

    title: str = Field(default="", max_length=255)
    app_id: int | None = None
