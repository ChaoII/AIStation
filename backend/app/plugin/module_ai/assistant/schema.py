from pydantic import BaseModel, Field


class AssistantChatSchema(BaseModel):
    message: str = Field(..., description="用户提问")


class AssistantUIStreamSchema(BaseModel):
    """AI SDK useChat 请求体（只取 messages，其余字段忽略）。"""

    messages: list[dict] = Field(default_factory=list)
