from pydantic import BaseModel, Field, field_validator

from app.core.base_schema import BaseSchema

# 特征维度上限：防御超大数组（512/1024/2048 均可覆盖）
_MAX_DIMENSION = 4096


class FaceGalleryEnrollSchema(BaseModel):
    """录入/更新底库条目：入参为已算好的人脸特征向量（边缘/云端算好）。"""

    id: int | None = Field(default=None, description="条目ID（提供时为更新，省略为新增）")
    name: str = Field(..., max_length=128, description="人员姓名/标签")
    person_no: str | None = Field(default=None, max_length=64, description="工号/自定义编号")
    model_key: str = Field(default="unknown", max_length=64, description="特征模型标识")
    description: str | None = Field(default=None, description="备注")
    face_image_url: str | None = Field(default=None, max_length=512, description="底图引用")
    embedding: list[float] = Field(..., min_length=1, description="人脸特征向量（L2 归一化）")
    dimension: int | None = Field(
        default=None, ge=1, le=_MAX_DIMENSION, description="特征维度（省略=按 embedding 长度）"
    )

    @field_validator("embedding")
    @classmethod
    def _check_embedding(cls, v: list[float]) -> list[float]:
        """向量必须非空、长度受限且全为有限数值（NaN/Inf 一律拒绝）。"""
        if len(v) > _MAX_DIMENSION:
            raise ValueError(f"特征维度超过上限 {_MAX_DIMENSION}")
        out: list[float] = []
        for x in v:
            val = float(x)
            if val != val or val in (float("inf"), float("-inf")):
                raise ValueError("特征向量必须为有限数值")
            out.append(val)
        return out

    @field_validator("dimension")
    @classmethod
    def _check_dimension(cls, v: int | None, info) -> int | None:
        """显式声明的维度必须与向量长度一致。"""
        emb = info.data.get("embedding")
        if v is not None and isinstance(emb, list) and len(emb) != v:
            raise ValueError(f"dimension={v} 与 embedding 长度 {len(emb)} 不一致")
        return v


class FaceGalleryMatchSchema(BaseModel):
    """底库比对请求：给定特征向量，返回相似度最高的若干条目。"""

    embedding: list[float] = Field(..., min_length=1, description="待比对特征向量")
    top_k: int = Field(default=5, ge=1, le=100, description="返回条数上限")
    threshold: float = Field(
        default=0.0, ge=-1.0, le=1.0, description="相似度下限（低于该值不返回）"
    )

    @field_validator("embedding")
    @classmethod
    def _check_embedding(cls, v: list[float]) -> list[float]:
        if len(v) > _MAX_DIMENSION:
            raise ValueError(f"特征维度超过上限 {_MAX_DIMENSION}")
        return [float(x) for x in v]


class FaceGalleryOutSchema(BaseSchema):
    """底库条目输出（不含特征向量，避免响应体膨胀；特征仅供服务端匹配用）。"""

    name: str
    person_no: str | None = None
    model_key: str = "unknown"
    dimension: int
    face_image_url: str | None = None
