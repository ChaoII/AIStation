from pydantic import BaseModel, Field


class AiToolCreateSchema(BaseModel):
    """新增工具：默认按自定义 HTTP 工具创建。"""

    name: str = Field(..., max_length=128)
    kind: str = Field(default="http", max_length=16)
    source: str | None = Field(default=None, max_length=16)
    config: dict | None = None
    method: str = Field(default="GET", max_length=8)
    url: str = Field(default="", max_length=512)
    headers: dict | None = None
    params_schema: dict | None = None
    code: str | None = Field(default="", description="Python 脚本源码（kind=script）")
    timeout: int = Field(default=10, ge=1, le=60, description="脚本执行超时（秒）")
    enabled: bool = True
    description: str | None = None


class AiToolUpdateSchema(BaseModel):
    """编辑工具：仅更新传入字段。"""

    name: str | None = Field(default=None, max_length=128)
    source: str | None = Field(default=None, max_length=16)
    config: dict | None = None
    method: str | None = Field(default=None, max_length=8)
    url: str | None = Field(default=None, max_length=512)
    headers: dict | None = None
    params_schema: dict | None = None
    code: str | None = None
    timeout: int | None = Field(default=None, ge=1, le=60)
    enabled: bool | None = None
    description: str | None = None


class AiToolToggleSchema(BaseModel):
    """启停工具。"""

    enabled: bool


class AiToolTestScriptSchema(BaseModel):
    """试运行脚本工具。"""

    args: dict | None = Field(default=None, description="传给 run(args) 的参数")
