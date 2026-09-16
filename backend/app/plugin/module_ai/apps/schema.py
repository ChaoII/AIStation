from pydantic import BaseModel, Field

OUTPUT_FORMATS: set[str] = {"text", "table", "report"}


class AiAppCreateSchema(BaseModel):
    """新增 AI 应用。"""

    name: str = Field(..., max_length=128)
    icon: str = Field(default="", max_length=64)
    description: str | None = None
    model_id: int | None = None
    prompt_id: int | None = None
    tools: list[str] = Field(default_factory=list)
    output_format: str = Field(default="text", max_length=16)
    input_schema: dict | None = None
    enabled: bool = True
    order: int = 0


class AiAppUpdateSchema(BaseModel):
    """编辑 AI 应用：仅更新传入字段。"""

    name: str | None = Field(default=None, max_length=128)
    icon: str | None = Field(default=None, max_length=64)
    description: str | None = None
    model_id: int | None = None
    prompt_id: int | None = None
    tools: list[str] | None = None
    output_format: str | None = Field(default=None, max_length=16)
    input_schema: dict | None = None
    enabled: bool | None = None
    order: int | None = None


class AiAppRunSchema(BaseModel):
    """运行应用请求体：UI 消息 + 提示词变量 + 可选会话。"""

    messages: list[dict] = Field(default_factory=list)
    variables: dict | None = None
    session_id: int | None = None
