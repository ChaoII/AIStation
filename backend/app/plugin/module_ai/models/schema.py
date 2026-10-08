from datetime import datetime

from pydantic import BaseModel, Field


class AiModelCreateSchema(BaseModel):
    name: str = Field(..., max_length=128, description="配置名称")
    provider: str = Field(default="openai_compatible", max_length=32, description="提供方协议")
    provider_id: int | None = Field(default=None, description="所属提供商ID")
    usage: str = Field(default="chat", max_length=16, description="用途 chat/assistant/embedding")
    capabilities: list | None = Field(default=None, description="能力标签")
    context_window: int | None = Field(default=None, description="上下文窗口")
    base_url: str = Field(default="", max_length=512, description="API 基址")
    api_key: str | None = Field(default=None, max_length=512, description="API Key")
    model: str = Field(default="", max_length=128, description="模型名")
    temperature: float = Field(default=0.3, description="温度")
    max_tokens: int = Field(default=2048, description="最大 token")
    enabled: bool = Field(default=True, description="是否启用")
    is_default: bool = Field(default=False, description="是否默认")
    extra_headers: dict | None = Field(default=None, description="自定义请求头")
    description: str | None = Field(default=None, max_length=255, description="备注")


class AiModelUpdateSchema(AiModelCreateSchema):
    name: str | None = Field(default=None, max_length=128, description="配置名称")


class AiModelTestSchema(BaseModel):
    id: int | None = Field(default=None, description="已保存配置ID（优先）")
    name: str | None = Field(default=None, description="配置名称（未传 id 时可用）")
    base_url: str | None = Field(default=None, description="临时测试用基址")
    api_key: str | None = Field(default=None, description="临时测试用 Key")
    model: str | None = Field(default=None, description="临时测试用模型名")
    extra_headers: dict | None = Field(default=None, description="临时测试用请求头")


class AiModelOutSchema(BaseModel):
    id: int
    name: str
    provider: str
    provider_id: int | None = None
    usage: str = "chat"
    capabilities: list | None = None
    context_window: int | None = None
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    enabled: bool
    is_default: bool
    extra_headers: dict | None = None
    description: str | None = None
    api_key_masked: str
    created_time: datetime | None = None
