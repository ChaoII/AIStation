from pydantic import BaseModel, Field


class AssistantChatSchema(BaseModel):
    message: str = Field(..., description="用户提问")
    knowledge_ids: list[int] | None = Field(default=None, description="关联知识库（RAG）")


class AssistantUIStreamSchema(BaseModel):
    """AI SDK useChat 请求体（只取 messages，其余字段忽略）。"""

    messages: list[dict] = Field(default_factory=list)
    session_id: int | None = None
    knowledge_ids: list[int] | None = Field(default=None, description="关联知识库（RAG）")
    model_id: int | None = Field(default=None, description="切换使用的模型配置ID（选项）")
    files: list[dict] | None = Field(
        default=None, description="上传文件：name/type/dataUrl（图片走视觉，文档抽取文本）"
    )
