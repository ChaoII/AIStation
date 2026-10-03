"""知识库 / 数据源的 Pydantic 模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AiKnowledgeBaseCreateSchema(BaseModel):
    name: str = Field(..., max_length=128)
    description: str | None = Field(default=None, max_length=1000)
    model_id: int | None = None
    file_type: str | None = Field(default="text", max_length=32)
    enabled: bool = True


class AiKnowledgeBaseUpdateSchema(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=1000)
    model_id: int | None = None
    file_type: str | None = Field(default=None, max_length=32)
    enabled: bool | None = None


class AiKnowledgeIngestSchema(BaseModel):
    file_name: str = Field(default="文本", max_length=256)
    content: str = Field(..., description="待入库文本内容")
    chunk_size: int = Field(default=500, ge=100, le=2000)
    overlap: int = Field(default=50, ge=0, le=400)
    strategy: str = Field(default="fixed", description="fixed/paragraph/sentence")


class AiKnowledgeUpdateChunkSchema(BaseModel):
    content: str = Field(..., min_length=1, description="分块内容")


class AiKnowledgeChunkAnnotateSchema(BaseModel):
    """分块标注：文本 + 类型（alias 别名 / anchor 锚点 / note 备注）。"""
    text: str = Field(..., min_length=1, max_length=512)
    kind: str = Field(default="alias", max_length=32, description="alias/anchor/note")


class AiKnowledgeEntityBindSchema(BaseModel):
    """实体绑定分块：给定要绑定的分块 id 列表。"""
    chunk_ids: list[int] = Field(default_factory=list)


class AiKnowledgeGraphRelationUpdateSchema(BaseModel):
    """图谱关系编辑。"""
    source: str | None = Field(default=None, max_length=256)
    target: str | None = Field(default=None, max_length=256)
    weight: int | None = Field(default=None, ge=1)


class AiKnowledgeSearchSchema(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    use_graph: bool = True
    mode: str = Field(default="hybrid", description="vector/fulltext/hybrid/graph/grep")
    vector_weight: float = Field(default=0.5, ge=0.0, le=1.0, description="混合检索：向量权重")
    fulltext_weight: float = Field(default=0.5, ge=0.0, le=1.0, description="混合检索：全文权重")


class AiDatasourceCreateSchema(BaseModel):
    name: str = Field(..., max_length=128)
    ds_type: str = Field(default="db", description="db/api")
    dialect: str | None = Field(default=None, max_length=32)
    uri: str | None = Field(default=None)
    api_config: dict | None = None
    knowledge_base_id: int | None = None
    enabled: bool = True


class AiDatasourceUpdateSchema(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    ds_type: str | None = None
    dialect: str | None = Field(default=None, max_length=32)
    uri: str | None = None
    api_config: dict | None = None
    knowledge_base_id: int | None = None
    enabled: bool | None = None


class AiDatasourceSyncSchema(BaseModel):
    """数据源同步：数据库查询 SQL 或 API 字段路径。"""

    table: str | None = Field(default=None, max_length=128, description="数据库表名/查询")
    limit: int = Field(default=50, ge=1, le=500)


class AiKnowledgeGraphEntitySchema(BaseModel):
    """图谱实体：名称 + 类型 + 权重。"""
    name: str = Field(..., max_length=256)
    etype: str | None = Field(default="keyword", max_length=64)
    weight: int = Field(default=1, ge=1)


class AiKnowledgeGraphRelationSchema(BaseModel):
    """图谱关系：源 + 目标 + 权重。"""
    source: str = Field(..., max_length=256)
    target: str = Field(..., max_length=256)
    weight: int = Field(default=1, ge=1)
