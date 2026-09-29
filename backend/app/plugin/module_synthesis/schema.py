"""数据合成模块的请求/响应 schema。"""
from pydantic import BaseModel, Field


class ProviderOut(BaseModel):
    key: str
    label: str
    description: str
    task_type: str
    classes: list[str]
    plate_types: list[dict] = Field(default_factory=list)
    disturbances: list[dict] = Field(default_factory=list)


class DisturbanceCfg(BaseModel):
    """各类扰动开关 + 参数区间；缺省 True 表示启用，params 键见 providers.disturbances。"""
    noise: bool = True
    mottle: bool = True
    occlusion: bool = True
    blur: bool = True
    motion_blur: bool = True
    photon: bool = True
    perspective: bool = True
    shadow: bool = True
    params: dict[str, list[float]] = Field(default_factory=dict, description="扰动参数区间 {参数名: [下限, 上限]}")


class PlateGenerateReq(BaseModel):
    """车牌合成请求。"""
    dataset_id: int | None = Field(default=None, description="目标数据集ID（提供则合成图入库）")
    count: int = Field(default=8, ge=1, le=100, description="生成数量")
    seed: int | None = Field(default=None, description="随机种子（固定可复现）")
    plate_type: str = Field(default="blue", description="车牌类型 key（见 providers.plate_types）")
    disturbances: DisturbanceCfg | None = Field(default=None, description="扰动开关")
    upload: bool = Field(default=True, description="是否写入 dataset")
    with_annotation: bool = Field(default=True, description="是否写入标注任务（含检测框）")
    width: int = Field(default=1920, description="画布宽")
    height: int = Field(default=1080, description="画布高")


class GeneratedItem(BaseModel):
    filename: str
    text: str = ""
    label: str = "plate"
    plate_type: str = "blue"
    bbox: dict = Field(default_factory=dict)
    char_boxes: list = Field(default_factory=list)
    width: int = 0
    height: int = 0
    object_key: str | None = None
    image_id: int | None = None
    preview_base64: str | None = None


class PlateGenerateResp(BaseModel):
    provider: str = "license_plate"
    job_id: int | None = None
    uploaded: bool
    items: list[GeneratedItem]


class JobOut(BaseModel):
    id: int
    provider: str
    name: str
    dataset_id: int | None
    params: dict = Field(default_factory=dict)
    status: str
    total: int
    done: int
    error: str | None
    results: list = Field(default_factory=list)
    created_time: str | None = None
