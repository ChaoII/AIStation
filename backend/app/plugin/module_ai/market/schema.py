"""市场查询/提交/分享/审核请求模型。"""
from pydantic import BaseModel, Field


class MarketItemQuerySchema(BaseModel):
    """市场商品列表查询：类型/分类/关键词/个人关系过滤 + 分页。"""

    type: str | None = Field(default=None, max_length=16, description="资产类型: tool/skill/mcp/plugin")
    category: str | None = Field(default=None, max_length=64, description="市场分类")
    keyword: str | None = Field(default=None, max_length=64, description="关键词（名称/描述）")
    favorite: bool = Field(default=False, description="只看我收藏的")
    installed: bool = Field(default=False, description="只看我安装的")
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=12, ge=1, le=100)


class MarketSubmitSchema(BaseModel):
    """提交市场：把个人真实资产快照为市场商品（进入待审核）。"""

    asset_type: str = Field(..., max_length=16, description="资产类型: tool/skill/mcp/plugin")
    source_id: int = Field(..., description="来源真实记录 id")
    name: str = Field(..., max_length=128)
    description: str | None = Field(default="", max_length=2000)
    icon: str | None = Field(default="", max_length=256)
    category: str | None = Field(default="", max_length=64)
    tags: list[str] | None = None
    version: str | None = Field(default="1.0", max_length=16)


class MarketReviewSchema(BaseModel):
    """审核：通过/驳回 + 意见。"""

    item_id: int
    action: str = Field(..., description="approve/reject")
    remark: str | None = Field(default="", max_length=500)


class MarketShareSchema(BaseModel):
    """点对点分享。"""

    item_id: int
    to_user_id: int
    message: str | None = Field(default="", max_length=255)
