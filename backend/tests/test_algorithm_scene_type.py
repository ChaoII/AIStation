"""算法 scene_type 字段测试。"""

from app.api.v1.module_video.algorithm.model import AlgorithmModel
from app.api.v1.module_video.algorithm.schema import (
    AlgorithmCreateSchema,
    AlgorithmOutSchema,
)


def test_scene_type_in_schemas():
    """创建/输出 Schema 均包含 scene_type 字段。"""
    assert "scene_type" in AlgorithmCreateSchema.model_fields
    assert "scene_type" in AlgorithmOutSchema.model_fields


def test_scene_type_in_model():
    """模型包含 scene_type 列，且允许为空。"""
    column = AlgorithmModel.__table__.c.scene_type
    assert column.nullable is True
    assert column.type.length == 64
