from pydantic import BaseModel, Field


class AssistantChatSchema(BaseModel):
    message: str = Field(..., description="用户提问")
