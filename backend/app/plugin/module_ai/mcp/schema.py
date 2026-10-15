"""MCP 服务器配置请求模型。"""
from pydantic import BaseModel, Field


class McpCreateSchema(BaseModel):
    """新增 MCP 服务器。"""

    name: str = Field(..., max_length=128)
    transport: str = Field(default="streamable-http", max_length=32, description="stdio/sse/streamable-http")
    command: str | None = Field(default="", max_length=512)
    args: list[str] | None = None
    env: dict | None = None
    url: str | None = Field(default="", max_length=512)
    headers: dict | None = None
    auth_type: str = Field(default="none", max_length=16, description="none/bearer/custom")
    enabled: bool = True
    description: str | None = None


class McpUpdateSchema(BaseModel):
    """编辑 MCP 服务器（仅更新传入字段）。"""

    name: str | None = Field(default=None, max_length=128)
    transport: str | None = Field(default=None, max_length=32)
    command: str | None = Field(default=None, max_length=512)
    args: list[str] | None = None
    env: dict | None = None
    url: str | None = Field(default=None, max_length=512)
    headers: dict | None = None
    auth_type: str | None = Field(default=None, max_length=16)
    enabled: bool | None = None
    description: str | None = None


class McpToggleSchema(BaseModel):
    """启停 MCP 服务器。"""

    enabled: bool
