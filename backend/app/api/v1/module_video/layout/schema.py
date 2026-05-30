
from pydantic import BaseModel, Field

from app.core.base_schema import BaseSchema


class LayoutCreateSchema(BaseModel):
    name: str = Field(..., max_length=64, description="布局名称")
    grid_type: str = Field(default="4", max_length=8, description="布局类型: 1/4/6/8/9/16")
    layout_config: dict | None = Field(default=None, description="窗口配置")
    is_default: bool = Field(default=False, description="是否默认")
    description: str | None = Field(default=None, max_length=255, description="描述")
    is_template: bool = Field(default=False, description="是否模板")
    patrol_interval: int | None = Field(default=None, ge=1, le=3600, description="轮巡间隔(秒)")


class LayoutUpdateSchema(LayoutCreateSchema):
    name: str | None = Field(default=None, max_length=64, description="布局名称")


class LayoutOutSchema(BaseSchema):
    name: str
    grid_type: str = "4"
    layout_config: dict | None = None
    is_default: bool = False
    description: str | None = None
    is_template: bool = False
    patrol_interval: int | None = None
