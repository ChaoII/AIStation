
from pydantic import BaseModel, Field, field_serializer, field_validator

from app.core.base_schema import BaseSchema, CommonSchema

# 出参密钥脱敏占位符（审计 #13）：键名命中密钥语义的标量值一律替换为它
REDACTED_VALUE = "******"

_SECRET_KEY_EXACT: frozenset[str] = frozenset(
    {
        "key",
        "iv",
        "nonce",
        "salt",
        "secret",
        "password",
        "passwd",
        "pwd",
        "passphrase",
        "token",
        "credential",
    }
)
_SECRET_KEY_FRAGMENTS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "api_key",
    "apikey",
    "private_key",
    "privatekey",
    "encrypt_key",
    "decrypt_key",
    "aes_key",
    "access_key",
    "secret_key",
    "sign_key",
    "signing_key",
)


def _is_secret_key(key: object) -> bool:
    """键名是否表达密钥语义（用于出参脱敏与更新还原）。"""
    if not isinstance(key, str):
        return False
    lowered = key.strip().lower()
    if lowered in _SECRET_KEY_EXACT:
        return True
    return any(frag in lowered for frag in _SECRET_KEY_FRAGMENTS)


def redact_model_file_config(value, *, _depth: int = 0):
    """递归脱敏 ``model_file_config`` 中密钥类字段的值（保留结构与非敏感字段）。"""
    if _depth > 6:
        return value
    if isinstance(value, dict):
        out: dict = {}
        for key, item in value.items():
            if _is_secret_key(key):
                out[key] = item if item in (None, "", [], {}) else REDACTED_VALUE
            else:
                out[key] = redact_model_file_config(item, _depth=_depth + 1)
        return out
    if isinstance(value, list):
        return [redact_model_file_config(item, _depth=_depth + 1) for item in value]
    return value


def restore_redacted_secrets(new_value, old_value):
    """把回传的脱敏占位符还原为库中真实值。

    前端编辑表单会原样回传（已脱敏的）``model_file_config``；若不在写库前还原，
    真实密钥会被占位符覆盖。仅当新值与占位符一致且旧值存在时才还原。
    """
    if isinstance(new_value, dict):
        old_dict = old_value if isinstance(old_value, dict) else {}
        out: dict = {}
        for key, item in new_value.items():
            if _is_secret_key(key) and item == REDACTED_VALUE:
                out[key] = old_dict.get(key, item)
            else:
                out[key] = restore_redacted_secrets(item, old_dict.get(key))
        return out
    if isinstance(new_value, list):
        old_list = old_value if isinstance(old_value, list) else []
        return [
            restore_redacted_secrets(item, old_list[i] if i < len(old_list) else None)
            for i, item in enumerate(new_value)
        ]
    return new_value


def _validate_model_name(value: str | None) -> str | None:
    """算法名会被拼入 Agent 请求路径，禁止路径分隔符/控制字符（审计 #15）。"""
    if value:
        if "/" in value or "\\" in value or any(ord(ch) < 0x20 for ch in value):
            raise ValueError("算法名称不能包含路径分隔符或控制字符")
    return value


class AlgorithmCreateSchema(BaseModel):
    name: str = Field(..., max_length=128, description="算法名称")
    code: str = Field(..., max_length=64, description="算法编码")
    version: str = Field(default="1.0.0", max_length=32, description="版本号")
    algorithm_type: str = Field(..., max_length=32, description="算法类型")
    scene_type: str | None = Field(default=None, max_length=64, description="场景码")
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

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str | None) -> str | None:
        return _validate_model_name(value)


class AlgorithmUpdateSchema(AlgorithmCreateSchema):
    name: str | None = Field(default=None, max_length=128, description="算法名称")
    code: str | None = Field(default=None, max_length=64, description="算法编码")


class AlgorithmOutSchema(BaseSchema):
    name: str
    code: str
    version: str = "1.0.0"
    algorithm_type: str
    scene_type: str | None = None
    model_path: str | None = None
    plugin_path: str | None = None
    # SP6-c：上一版本（回滚用），仅输出；由热更新/回滚接口维护，不允许直接写入
    previous_model_path: str | None = None
    previous_version: str | None = None
    model_file_config: dict | None = None
    runtime_config: dict | None = None
    preset_params: dict | None = None
    param_meta: dict | None = None
    input_params: dict | None = None
    output_schema: dict | None = None
    status: bool = True
    description: str | None = None

    @field_serializer("model_file_config")
    def _serialize_model_file_config(self, value):
        """出参脱敏：不回显模型配置中的加密/解密密钥（审计 #13）。"""
        return redact_model_file_config(value)


class AlgorithmTaskCreateSchema(BaseModel):
    camera_id: int = Field(..., description="摄像机ID")
    algorithm_id: int = Field(..., description="算法ID")
    edge_device_id: int | None = Field(default=None, description="边缘设备ID（空=纯云端本机）")
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
    edge_device_id: int | None = None
    stream_type: str = "SUB"
    detect_region: dict | None = None
    sensitivity: int = 50
    schedule_json: dict | None = None
    runtime_overrides: dict | None = None
    params_overrides: dict | None = None
    status: str = "STOPPED"
    error_log: str | None = None
    camera: CommonSchema | None = None
    algorithm: CommonSchema | None = None
