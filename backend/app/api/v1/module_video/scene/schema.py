"""场景注册表输出 schema。"""
from pydantic import BaseModel, Field


class SceneOutSchema(BaseModel):
    """场景（任务类型）定义输出。"""

    code: str = Field(..., description="场景码")
    name: str = Field(..., description="场景名称")
    category: str = Field(..., description="场景分类")
    scene_type: str = Field(..., description="场景类型（写入 TaskConfig.scene_type）")
    model_families: list[str] = Field(default_factory=list, description="所需模型族")
    pipeline: list[dict] = Field(default_factory=list, description="模型 pipeline 定义")
    param_schema: list[dict] = Field(default_factory=list, description="参数 schema")
    default_rule: dict = Field(default_factory=dict, description="默认规则")
    needs_tracking: bool = Field(default=False, description="是否需要跟踪")
    description: str = Field(default="", description="场景说明")
