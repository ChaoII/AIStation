from pydantic import BaseModel, Field, field_validator

BLOCK_TYPES: set[str] = {"system", "context", "instruction", "example", "output"}


def _validate_blocks(value: list | None) -> list:
    """校验块列表：每项为 dict，type 合法，content 为字符串。"""
    result = value or []
    for item in result:
        if not isinstance(item, dict):
            raise ValueError("blocks 每一项必须是对象")
        block_type = item.get("type")
        if block_type not in BLOCK_TYPES:
            raise ValueError(f"非法的块类型: {block_type}")
        content = item.get("content", "")
        if not isinstance(content, str):
            raise ValueError("块内容必须是字符串")
    return result


class AiPromptCreateSchema(BaseModel):
    name: str = Field(..., max_length=128)
    category: str = Field(default="", max_length=32)
    blocks: list[dict] = Field(default_factory=list)
    variables: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("blocks")
    @classmethod
    def _check_blocks(cls, value: list | None) -> list:
        return _validate_blocks(value)


class AiPromptUpdateSchema(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    category: str | None = Field(default=None, max_length=32)
    blocks: list[dict] | None = None
    variables: list[str] | None = None
    enabled: bool | None = None
    version: int | None = None

    @field_validator("blocks")
    @classmethod
    def _check_blocks(cls, value: list | None) -> list | None:
        if value is None:
            return None
        return _validate_blocks(value)
