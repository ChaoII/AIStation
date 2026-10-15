"""AI 能力插件请求模型。"""
from pydantic import BaseModel, Field


class PluginCreateSchema(BaseModel):
    """新增插件。"""

    key: str = Field(..., max_length=64)
    label: str | None = Field(default="", max_length=128)
    kind: str = Field(default="custom", max_length=32, description="builtin/custom")
    config: dict | None = None
    config_schema: dict | None = None
    enabled: bool = True
    description: str | None = None


class PluginUpdateSchema(BaseModel):
    """编辑插件（仅更新传入字段）。"""

    label: str | None = Field(default=None, max_length=128)
    config: dict | None = None
    config_schema: dict | None = None
    enabled: bool | None = None
    description: str | None = None


class PluginToggleSchema(BaseModel):
    """启停插件。"""

    enabled: bool
