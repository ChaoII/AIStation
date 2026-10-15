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


class AiSkillImportSchema(BaseModel):
    """导入技能（粘贴 SKILL.md 内容）。"""

    content: str = Field(..., description="SKILL.md 全文（可含 YAML frontmatter）")
    name: str | None = Field(default=None, max_length=128, description="覆盖技能名")
    category: str | None = Field(default=None, max_length=64, description="导入到哪个分类")
    source: str | None = Field(default="SkillHub", max_length=64, description="来源标注（记录用）")
