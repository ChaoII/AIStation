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
    strategy: str = Field(
        default="fixed", description="fixed/paragraph/sentence/heading"
    )
    parent_child: bool = Field(default=False, description="是否启用父子分块")
    chunk_unit: str = Field(default="char", description="切分口径：char/token")


class AiKnowledgeUpdateChunkSchema(BaseModel):
    content: str = Field(..., min_length=1, description="分块内容")


class AiKnowledgeChunkAnnotateSchema(BaseModel):
    """分块标注：文本 + 类型（alias 别名 / anchor 锚点 / note 备注）+ 来源上下文。"""
    text: str = Field(..., min_length=1, max_length=512)
    kind: str = Field(default="alias", max_length=32, description="alias/anchor/note")
    query: str | None = Field(default=None, max_length=1000, description="触发标注的查询")
    source: str = Field(default="manual", max_length=32, description="manual/search/auto/graph")


class AiKnowledgeEntityBindSchema(BaseModel):
    """实体绑定分块：给定要绑定的分块 id 列表。"""
    chunk_ids: list[int] = Field(default_factory=list)


class AiKnowledgeGraphRelationUpdateSchema(BaseModel):
    """图谱关系编辑。"""
    source: str | None = Field(default=None, max_length=256)
    target: str | None = Field(default=None, max_length=256)
    weight: int | None = Field(default=None, ge=1)
    rtype: str | None = Field(default=None, max_length=64)


class AiKnowledgeSearchSchema(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    use_graph: bool = True
    mode: str = Field(default="hybrid", description="vector/fulltext/hybrid/graph/grep")
    vector_weight: float = Field(default=0.5, ge=0.0, le=1.0, description="混合检索：向量权重")
    fulltext_weight: float = Field(default=0.5, ge=0.0, le=1.0, description="混合检索：全文权重")
    use_weighted: bool = Field(default=False, description="是否用归一化加权（默认 RRF）")
    min_score: float = Field(default=0.0, ge=-1.0, le=1.0, description="向量相似度下限")
    use_rerank: bool = Field(default=True, description="是否启用 rerank 精排")
    filters: dict | None = Field(default=None, description="元数据过滤：file_name/document_id/file_type")
    context_tokens: int | None = Field(default=None, ge=100, le=20000, description="上下文 token 预算")
    rewrite: str = Field(default="off", description="查询改写：off/multi_query/hyde")


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
    """图谱实体：名称 + 类型 + 权重 + 备注。"""
    name: str = Field(..., max_length=256)
    etype: str | None = Field(default="keyword", max_length=64)
    weight: int = Field(default=1, ge=1)
    description: str | None = Field(default=None, max_length=1000, description="实体备注/描述")


class AiKnowledgeGraphRelationSchema(BaseModel):
    """图谱关系：源 + 目标 + 权重 + 关系类型。"""
    source: str = Field(..., max_length=256)
    target: str = Field(..., max_length=256)
    weight: int = Field(default=1, ge=1)
    rtype: str | None = Field(default="related", max_length=64, description="关系类型/语义")


class AiKnowledgeGraphLayoutItemSchema(BaseModel):
    """单个节点坐标。"""
    id: int
    x: float
    y: float


class AiKnowledgeGraphLayoutSchema(BaseModel):
    """保存图谱布局：节点坐标列表。"""
    items: list[AiKnowledgeGraphLayoutItemSchema] = Field(default_factory=list)


class AiRelationTypeCreateSchema(BaseModel):
    """关系类型模板。"""
    name: str = Field(..., min_length=1, max_length=64)
    color: str | None = Field(default=None, max_length=16)
