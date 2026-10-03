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
    """知识分块：内容 + 向量（可移植余弦，dimension 过滤）+ 用户标注。"""

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
    annotations: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=None,
        comment="用户标注（[{text,kind}]），参与向量+全文+grep 检索以提升召回",
    )
    meta: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="元数据"
    )
    vector: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="向量（JSON 列表，含标注文本）"
    )
    dimension: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="向量维度"
    )


class AiKnowledgeEntityChunkModel(ModelMixin):
    """图谱实体 ↔ 知识分块 多对多绑定（用于图谱检索回溯分块）。"""

    __tablename__ = "ai_knowledge_entity_chunks"
    __table_args__ = (
        {"comment": "图谱实体-分块绑定表"},
    )

    entity_id: Mapped[int] = mapped_column(
        ForeignKey("ai_knowledge_entities.id"), nullable=False, comment="实体 ID"
    )
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("ai_knowledge_chunks.id"), nullable=False, comment="分块 ID"
    )


class AiChunkAnnotationLogModel(ModelMixin):
    """分块标注台账：记录每次标注的来源（查询/手动/图谱）与操作人，形成 QA 闭环。"""

    __tablename__ = "ai_chunk_annotation_logs"
    __table_args__ = ({"comment": "AI 分块标注台账表"},)

    knowledge_base_id: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="知识库 ID"
    )
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("ai_knowledge_chunks.id"), nullable=False, comment="分块 ID"
    )
    action: Mapped[str] = mapped_column(
        String(16), default="add", comment="动作: add/remove"
    )
    text: Mapped[str] = mapped_column(Text, nullable=False, comment="标注文本")
    kind: Mapped[str | None] = mapped_column(
        String(32), default="alias", comment="类型: alias/anchor/note"
    )
    query: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None, comment="触发标注的查询"
    )
    source: Mapped[str | None] = mapped_column(
        String(32), default="manual", comment="来源: manual/search/auto/graph"
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="操作用户 ID"
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


class AiKnowledgeEntityModel(ModelMixin):
    """知识图谱实体（GraphRAG 节点）。"""

    __tablename__ = "ai_knowledge_entities"
    __table_args__ = ({"comment": "AI 知识库图谱实体表"},)

    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("ai_knowledge_bases.id"), nullable=False, comment="知识库 ID"
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False, comment="实体名")
    etype: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default="keyword", comment="实体类型"
    )
    weight: Mapped[int] = mapped_column(Integer, default=1, comment="实体权重（出现次数）")


class AiKnowledgeRelationModel(ModelMixin):
    """知识图谱关系（GraphRAG 边）。"""

    __tablename__ = "ai_knowledge_relations"
    __table_args__ = ({"comment": "AI 知识库图谱关系表"},)

    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("ai_knowledge_bases.id"), nullable=False, comment="知识库 ID"
    )
    source: Mapped[str] = mapped_column(String(256), nullable=False, comment="源实体")
    target: Mapped[str] = mapped_column(String(256), nullable=False, comment="目标实体")
    weight: Mapped[int] = mapped_column(Integer, default=1, comment="共现权重")
