"""知识库 / 数据源 RAG 的数据模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiKnowledgeCategoryModel(ModelMixin, UserMixin):
    """知识库分类：树形分组（父级 + 同级排序 + 负责人），供知识库左侧分类树使用。"""

    __tablename__ = "ai_knowledge_categories"
    __table_args__ = ({"comment": "AI 知识库分类表"},)

    name: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, comment="分类名称"
    )
    parent_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="父分类 ID"
    )
    owner: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None, comment="负责人"
    )
    remark: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="备注"
    )
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="同级排序")


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
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_knowledge_categories.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        comment="知识库分类 ID",
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
    document_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="来源文档 ID（引用溯源）"
    )
    start_line: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="分块在原文起始行（引用溯源）"
    )
    page: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="分块所在页码（PDF/Word，引用溯源）"
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, comment="分块序号")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="分块内容")
    parent_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="父块 ID（子块指向父块）"
    )
    is_parent: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否父块（父块不参与召回，仅用于上下文回填）"
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None, comment="内容哈希（去重/幂等）"
    )
    vector_model: Mapped[str | None] = mapped_column(
        String(128), nullable=True, default=None, comment="生成该向量的模型名（换模型失效判定）"
    )
    token_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="token 估算数（上下文预算用）"
    )
    char_start: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="原文起始字符偏移"
    )
    char_end: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="原文结束字符偏移"
    )
    search_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None,
        comment="正文+标注的可索引文本（全文检索唯一入口）",
    )
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


class AiSearchLogModel(ModelMixin):
    """知识库检索日志：用于检索趋势统计与命中率分析。"""

    __tablename__ = "ai_search_logs"
    __table_args__ = ({"comment": "AI 知识库检索日志表"},)

    knowledge_base_id: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="知识库 ID"
    )
    query: Mapped[str] = mapped_column(Text, nullable=False, comment="检索查询")
    mode: Mapped[str | None] = mapped_column(
        String(32), default="hybrid", comment="检索模式"
    )
    top_k: Mapped[int] = mapped_column(Integer, default=5, comment="请求条数")
    hit_count: Mapped[int] = mapped_column(Integer, default=0, comment="命中条数")
    engines: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="命中的引擎集合"
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="检索用户 ID"
    )


class AiKnowledgeDocumentModel(ModelMixin):
    """知识库文档（wikiLLM / ima 式文档管理）：上传解析→分块→索引。"""

    __tablename__ = "ai_knowledge_documents"
    __table_args__ = ({"comment": "AI 知识库文档表"},)

    knowledge_base_id: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="知识库 ID"
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False, comment="文档名")
    file_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default="txt", comment="类型: txt/md/docx/pdf"
    )
    size: Mapped[int] = mapped_column(Integer, default=0, comment="文件大小(字节)")
    content: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="提取的全文"
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, comment="分块数")
    doc_status: Mapped[str] = mapped_column(
        String(16), default="ready", comment="状态: ready/error"
    )
    file_path: Mapped[str | None] = mapped_column(
        String(512), nullable=True, default=None, comment="原始文件相对路径(旧本地存储，兼容)"
    )
    object_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True, default=None, comment="RustFS 对象存储 key"
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
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="实体备注/描述"
    )
    layout: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="节点坐标 {x,y}（布局记忆）"
    )


class AiRelationTypeTemplateModel(ModelMixin):
    """图谱关系类型常用模板（可维护）。"""

    __tablename__ = "ai_relation_types"
    __table_args__ = ({"comment": "AI 图谱关系类型模板表"},)

    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="关系类型名")
    color: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default="#a0a6ad", comment="连线颜色（可选）"
    )


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
    rtype: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default="related", comment="关系类型/语义描述（线上显示）"
    )


class AiRagTaskModel(ModelMixin, UserMixin):
    """RAG 后台任务（文档入库/重建索引/数据源同步/评测运行）。

    状态机：``pending → running → succeeded | failed | canceled``。
    """

    __tablename__ = "ai_rag_tasks"
    __table_args__ = ({"comment": "AI RAG 后台任务表"},)

    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="document_ingest", comment="任务类型"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending",
        comment="状态 pending/running/succeeded/failed/canceled",
    )
    kb_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None, comment="知识库 ID")
    document_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None, comment="文档 ID"
    )
    payload: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="任务参数"
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="进度 0-100")
    step: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None, comment="当前步骤"
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None, comment="进度信息")
    error: Mapped[str | None] = mapped_column(Text, nullable=True, default=None, comment="失败原因")
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否请求取消"
    )
    started_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )
    finished_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )


class AiEvalSetModel(ModelMixin, UserMixin):
    """检索评测集（一组查询 + 金标准分块）。"""

    __tablename__ = "ai_eval_sets"
    __table_args__ = ({"comment": "AI 检索评测集"},)

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    kb_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)


class AiEvalItemModel(ModelMixin):
    """评测条目：查询 + 期望命中的分块 id（或文件名）。"""

    __tablename__ = "ai_eval_items"
    __table_args__ = ({"comment": "AI 检索评测条目"},)

    set_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    expected_chunk_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)
    expected_files: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)
    note: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)


class AiEvalRunModel(ModelMixin, UserMixin):
    """评测运行记录：配置 + 指标。"""

    __tablename__ = "ai_eval_runs"
    __table_args__ = ({"comment": "AI 检索评测运行记录"},)

    set_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    kb_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    error: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
