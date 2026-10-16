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


class WorkspaceCronCreateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="任务名称")
    description: str = Field(default="", max_length=512)
    cron: str = Field(..., description="cron 表达式（5 段）")
    target_type: str = Field(default="agent", description="agent/workflow/app")
    target_id: int = Field(default=0, description="执行目标 ID")
    category_id: int | None = Field(default=None)
    enabled: bool = Field(default=False)


class WorkspaceCronUpdateSchema(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    cron: str | None = None
    target_type: str | None = None
    target_id: int | None = None
    category_id: int | None = None
    enabled: bool | None = None
