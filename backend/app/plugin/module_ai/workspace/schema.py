"""AI 工作台分类/条目 schema。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class WorkspaceCategoryCreateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="分类名称")
    parent_id: int | None = Field(default=None, description="父分类ID（空为顶级）")
    icon: str | None = Field(default="", description="图标")
    color: str | None = Field(default="", description="主题色")
    sort: int = Field(default=0, description="排序")


class WorkspaceCategoryUpdateSchema(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    icon: str | None = None
    color: str | None = None
    sort: int | None = None
