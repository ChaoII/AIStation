from pydantic import BaseModel, Field


class AiToolCreateSchema(BaseModel):
    """新增工具：默认按自定义 HTTP 工具创建。"""

    name: str = Field(..., max_length=128)
    kind: str = Field(default="http", max_length=16)
    method: str = Field(default="GET", max_length=8)
    url: str = Field(default="", max_length=512)
    headers: dict | None = None
    params_schema: dict | None = None
    enabled: bool = True
    description: str | None = None


class AiToolUpdateSchema(BaseModel):
    """编辑工具：仅更新传入字段。"""

    name: str | None = Field(default=None, max_length=128)
    method: str | None = Field(default=None, max_length=8)
    url: str | None = Field(default=None, max_length=512)
    headers: dict | None = None
    params_schema: dict | None = None
    enabled: bool | None = None
    description: str | None = None


class AiToolToggleSchema(BaseModel):
    """启停工具。"""

    enabled: bool
