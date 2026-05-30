
from pydantic import BaseModel, Field

from app.core.base_schema import BaseSchema, CommonSchema


class AlgorithmCreateSchema(BaseModel):
    name: str = Field(..., max_length=128, description="算法名称")
    code: str = Field(..., max_length=64, description="算法编码")
    version: str = Field(default="1.0.0", max_length=32, description="版本号")
    algorithm_type: str = Field(..., max_length=32, description="算法类型")
    model_path: str | None = Field(default=None, max_length=512, description="模型文件路径")
    plugin_path: str | None = Field(default=None, max_length=512, description="插件路径")
    model_file_config: dict | None = Field(default=None, description="模型配置（格式、加密密钥等）")
    runtime_config: dict | None = Field(default=None, description="运行时配置（推理引擎、GPU、线程等）")
    preset_params: dict | None = Field(default=None, description="预设算法参数（阈值等）")
    param_meta: dict | None = Field(default=None, description="参数元数据定义（标签、类型、选项、单位、说明等）")
    input_params: dict | None = Field(default=None, description="输入参数配置")
    output_schema: dict | None = Field(default=None, description="输出数据格式")
    status: bool = Field(default=True, description="是否启用")
    description: str | None = Field(default=None, max_length=255, description="描述")


class AlgorithmUpdateSchema(AlgorithmCreateSchema):
    name: str | None = Field(default=None, max_length=128, description="算法名称")
    code: str | None = Field(default=None, max_length=64, description="算法编码")


class AlgorithmOutSchema(BaseSchema):
    name: str
    code: str
    version: str = "1.0.0"
    algorithm_type: str
    model_path: str | None = None
    plugin_path: str | None = None
    model_file_config: dict | None = None
    runtime_config: dict | None = None
    preset_params: dict | None = None
    param_meta: dict | None = None
    input_params: dict | None = None
    output_schema: dict | None = None
    status: bool = True
    description: str | None = None


class AlgorithmTaskCreateSchema(BaseModel):
    camera_id: int = Field(..., description="摄像机ID")
    algorithm_id: int = Field(..., description="算法ID")
    stream_type: str = Field(default="SUB", description="分析码流")
    detect_region: dict | None = Field(default=None, description="检测区域")
    sensitivity: int = Field(default=50, ge=1, le=100, description="灵敏度")
    schedule_json: dict | None = Field(default=None, description="生效时间段")
    runtime_overrides: dict | None = Field(default=None, description="运行时参数覆盖值")
    params_overrides: dict | None = Field(default=None, description="算法参数覆盖值")
    status: str = Field(default="STOPPED", description="状态")
    description: str | None = Field(default=None, max_length=255, description="描述")


class AlgorithmTaskUpdateSchema(AlgorithmTaskCreateSchema):
    camera_id: int | None = Field(default=None, description="摄像机ID")
    algorithm_id: int | None = Field(default=None, description="算法ID")


class AlgorithmTaskOutSchema(BaseSchema):
    camera_id: int
    algorithm_id: int
    stream_type: str = "SUB"
    detect_region: dict | None = None
    sensitivity: int = 50
    schedule_json: dict | None = None
    runtime_overrides: dict | None = None
    params_overrides: dict | None = None
    status: str = "STOPPED"
    camera: CommonSchema | None = None
    algorithm: CommonSchema | None = None
