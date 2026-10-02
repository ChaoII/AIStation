"""技能广场的 Pydantic 模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AiSkillCreateSchema(BaseModel):
    name: str = Field(..., max_length=128)
    description: str | None = Field(default=None, max_length=1000)
    content: str | None = None
    skill_type: str = Field(default="tool", description="instruction/tool/custom")
    category: str | None = Field(default=None, max_length=64)
    author: str | None = Field(default=None, max_length=64)
    version: str | None = Field(default=None, max_length=16)
    scripts: dict | None = None
    config: dict | None = None
    icon: str | None = Field(default=None, max_length=256)
    featured: bool = False
    sort_order: int = 0
    enabled: bool = True


class AiSkillUpdateSchema(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=1000)
    content: str | None = None
    skill_type: str | None = None
    category: str | None = Field(default=None, max_length=64)
    author: str | None = Field(default=None, max_length=64)
    version: str | None = Field(default=None, max_length=16)
    scripts: dict | None = None
    config: dict | None = None
    icon: str | None = Field(default=None, max_length=256)
    featured: bool | None = None
    sort_order: int | None = None
    enabled: bool | None = None
