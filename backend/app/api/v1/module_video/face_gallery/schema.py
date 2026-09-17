from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.base_schema import BaseSchema

# 特征维度上限：防御超大数组（512/1024/2048 均可覆盖）
_MAX_DIMENSION = 4096
# 底库类型：face=人脸（FACE_REC/STRANGER）；reid=跨镜重识别（REID_TRACK）
_KINDS = {"face", "reid"}


class FaceGalleryEnrollSchema(BaseModel):
    """录入/更新底库条目：入参为已算好的特征向量（边缘/云端算好）。

    新增（无 id）时 ``embedding`` 必填；按 id 更新时 ``embedding`` 可省略
    （仅改名/工号/底图引用，特征保持不变）。
    ``kind`` 区分入库类型（缺省 face 兼容旧调用；按 id 更新省略则不改动原类型）。
    """

    id: int | None = Field(default=None, description="条目ID（提供时为更新，省略为新增）")
    name: str = Field(..., max_length=128, description="人员姓名/标签")
    person_no: str | None = Field(default=None, max_length=64, description="工号/自定义编号")
    kind: str | None = Field(
        default=None, description="底库类型：face=人脸（默认）/ reid=跨镜重识别"
    )
    model_key: str = Field(default="unknown", max_length=64, description="特征模型标识")
    description: str | None = Field(default=None, description="备注")
    face_image_url: str | None = Field(default=None, max_length=512, description="底图引用")
    embedding: list[float] | None = Field(
        default=None, min_length=1, description="特征向量（L2 归一化；更新时可省略）"
    )
    dimension: int | None = Field(
        default=None, ge=1, le=_MAX_DIMENSION, description="特征维度（省略=按 embedding 长度）"
    )

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v: str | None) -> str | None:
        """kind 仅接受 face/reid（大小写不敏感）；缺省 None 由服务层按旧值/默认处理。"""
        if v is None:
            return None
        key = str(v).strip().lower()
        if key not in _KINDS:
            raise ValueError(f"kind 仅支持 {sorted(_KINDS)}，实际 {v!r}")
        return key

    @field_validator("embedding")
    @classmethod
    def _check_embedding(cls, v: list[float] | None) -> list[float] | None:
        """向量必须非空、长度受限且全为有限数值（NaN/Inf 一律拒绝）。"""
        if v is None:
            return None
        if len(v) > _MAX_DIMENSION:
            raise ValueError(f"特征维度超过上限 {_MAX_DIMENSION}")
        out: list[float] = []
        for x in v:
            val = float(x)
            if val != val or val in (float("inf"), float("-inf")):
                raise ValueError("特征向量必须为有限数值")
            out.append(val)
        return out

    @model_validator(mode="after")
    def _check_required_and_dimension(self) -> "FaceGalleryEnrollSchema":
        """新增必须有特征；显式维度与向量长度必须一致。"""
        if self.id is None and not self.embedding:
            raise ValueError("新增底库条目必须提供 embedding")
        if self.embedding is not None and self.dimension is not None:
            if len(self.embedding) != self.dimension:
                raise ValueError(
                    f"dimension={self.dimension} 与 embedding 长度 {len(self.embedding)} 不一致"
                )
        return self


class FaceGalleryMatchSchema(BaseModel):
    """底库比对请求：给定特征向量，返回同类底库中相似度最高的若干条目。"""

    embedding: list[float] = Field(..., min_length=1, description="待比对特征向量")
    kind: str = Field(default="face", description="比对底库类型：face（默认）/ reid")
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

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v: str) -> str:
        key = str(v).strip().lower()
        if key not in _KINDS:
            raise ValueError(f"kind 仅支持 {sorted(_KINDS)}，实际 {v!r}")
        return key


class FaceGalleryOutSchema(BaseSchema):
    """底库条目输出（不含特征向量，避免响应体膨胀；特征仅供服务端匹配用）。"""

    name: str
    person_no: str | None = None
    kind: str = "face"
    model_key: str = "unknown"
    dimension: int
    face_image_url: str | None = None
