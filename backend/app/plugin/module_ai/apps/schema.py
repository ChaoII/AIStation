from pydantic import BaseModel, Field

OUTPUT_FORMATS: set[str] = {"text", "table", "report"}


class AiAppCreateSchema(BaseModel):
    """新增 AI 应用（统一可配置组件）。"""

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
    app_type: str = Field(default="chat", max_length=16, description="组件类型: chat/agent/workflow/kb")
    kb_id: int | None = Field(default=None, description="绑定知识库ID(类型=kb)")
    workflow_id: int | None = Field(default=None, description="绑定工作流ID(类型=workflow或有工作流)")
    temperature: float | None = Field(default=None, ge=0, le=2, description="温度")
    max_tokens: int | None = Field(default=None, ge=64, description="最大输出token")
    context_window: int | None = Field(default=None, ge=0, description="上下文窗口")
    system_prompt: str | None = Field(default=None, description="自定义系统提示词")
    tags: list | None = Field(default=None, description="标签")
    memory: bool = Field(default=True, description="多轮记忆")
    timeout: int = Field(default=60, ge=5, le=600, description="超时(秒)")


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
    app_type: str | None = Field(default=None, max_length=16)
    kb_id: int | None = None
    workflow_id: int | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    context_window: int | None = None
    system_prompt: str | None = None
    tags: list | None = None
    memory: bool | None = None
    timeout: int | None = None


class AiAppRunSchema(BaseModel):
    """运行应用请求体：UI 消息 + 提示词变量 + 可选会话。"""

    messages: list[dict] = Field(default_factory=list)
    variables: dict | None = None
    session_id: int | None = None
