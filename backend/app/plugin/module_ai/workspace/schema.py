"""AI 工作台分类/条目 schema。"""
from __future__ import annotations

from typing import Any

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
    trigger: str | None = Field(default=None, description="触发类型：cron / interval / date / now")
    trigger_args: Any | None = Field(
        default=None,
        description="触发参数：cron 5 段串 / interval 对象或 JSON 串 / date 时间串 / now 为 null",
    )
    cron: str | None = Field(
        default=None, description="兼容字段：仅 cron 类型有值，仅在 trigger 缺省时解读"
    )
    target_type: str = Field(default="agent", description="agent/workflow/app")
    target_id: int = Field(default=0, description="执行目标 ID")
    category_id: int | None = Field(default=None)
    enabled: bool = Field(default=False)


class WorkspaceCronUpdateSchema(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    trigger: str | None = Field(default=None, description="触发类型：cron / interval / date / now")
    trigger_args: Any | None = Field(default=None, description="触发参数（按 trigger 解释）")
    cron: str | None = Field(
        default=None, description="兼容字段（仅 cron 类型；仅在 trigger 缺省时解读）"
    )
    target_type: str | None = None
    target_id: int | None = None
    category_id: int | None = None
    enabled: bool | None = None
