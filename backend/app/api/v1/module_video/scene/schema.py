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
    requires_classification: bool = Field(
        default=False, description="是否依赖边缘把分类结果写入事件（未落地时置灰）"
    )
    requires_keypoints: bool = Field(
        default=False, description="是否依赖边缘把姿态关键点写入事件（未落地时置灰）"
    )
    requires_attributes: bool = Field(
        default=False, description="是否依赖边缘把人脸属性/活体分数写入事件（未落地时置灰）"
    )
    requires_depth: bool = Field(
        default=False, description="是否依赖边缘把深度值写入事件（未落地时置灰）"
    )
    limitations: list[str] = Field(
        default_factory=list, description="已知限制说明（如叶子规则未实现），与阻断原因一并展示"
    )
    required_assets: list[str] = Field(default_factory=list, description="所需云端外部资产")
    edge_supported: bool = Field(
        default=True, description="所需模型族是否已由边缘 Agent 上报（历史字段）"
    )
    configurable: bool = Field(
        default=True, description="是否可配置（模型族 + 默认规则叶子均已就绪，选中即可保存成功）"
    )
    unsupported_reason: str = Field(default="", description="不可配置原因（可配置时为空）")
    blockers: list[str] = Field(
        default_factory=list, description="不可配置的数据驱动原因清单（缺族/缺资产/缺叶子，可配置时为空）"
    )
