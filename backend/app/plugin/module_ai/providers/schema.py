from pydantic import BaseModel, Field


class AiProviderCreateSchema(BaseModel):
    name: str = Field(..., max_length=128)
    protocol: str = Field(default="openai", max_length=32)
    base_url: str = Field(default="", max_length=512)
    api_key: str | None = Field(default=None, max_length=512)
    extra_headers: dict | None = None
    enabled: bool = True
    description: str | None = Field(default=None, max_length=255)


class AiProviderUpdateSchema(AiProviderCreateSchema):
    name: str | None = Field(default=None, max_length=128)


class AiProviderOutSchema(BaseModel):
    id: int
    name: str
    protocol: str
    base_url: str
    enabled: bool
    extra_headers: dict | None = None
    description: str | None = None
    api_key_masked: str = ""
