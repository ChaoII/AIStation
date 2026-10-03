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


class AiKnowledgeSearchSchema(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    use_graph: bool = True


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
