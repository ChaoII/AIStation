"""知识库 / 数据源 RAG 的数据模型。"""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiKnowledgeBaseModel(ModelMixin, UserMixin):
    """知识库：上传文档→分块→向量化→检索（RAG）。"""

    __tablename__ = "ai_knowledge_bases"
    __table_args__ = ({"comment": "AI 知识库表"},)

    name: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, comment="知识库名称"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="描述"
    )
    model_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="嵌入模型 ID（可选）"
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="分块数量"
    )
    file_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default="text", comment="内容类型"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")


class AiKnowledgeChunkModel(ModelMixin):
    """知识分块：内容 + 向量（可移植余弦，dimension 过滤）。"""

    __tablename__ = "ai_knowledge_chunks"
    __table_args__ = ({"comment": "AI 知识分块表"},)

    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("ai_knowledge_bases.id"), nullable=False, comment="知识库 ID"
    )
    file_name: Mapped[str | None] = mapped_column(
        String(256), nullable=True, default="", comment="来源文件名"
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, comment="分块序号")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="分块内容")
    meta: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="元数据"
    )
    vector: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="向量（JSON 列表）"
    )
    dimension: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="向量维度"
    )


class AiDatasourceModel(ModelMixin, UserMixin):
    """数据源：数据库（SQL）或 API，可同步到知识库。"""

    __tablename__ = "ai_datasources"
    __table_args__ = ({"comment": "AI 数据源表"},)

    name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="数据源名称"
    )
    ds_type: Mapped[str] = mapped_column(
        String(16), default="db", comment="类型: db/api"
    )
    dialect: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default="postgresql", comment="数据库方言"
    )
    uri: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="连接 URI 或 API URL"
    )
    api_config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="API 配置（headers/字段路径等）"
    )
    knowledge_base_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_knowledge_bases.id"), nullable=True, default=None,
        comment="同步目标知识库"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
