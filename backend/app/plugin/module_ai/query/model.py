"""智能问数：语义层(指标/术语) + 数据源 + 会话/问答记录模型。"""
from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiQueryDatasourceModel(ModelMixin, UserMixin):
    """自定义问数数据源（数据库/文件/接口）。"""

    __tablename__ = "ai_query_datasources"
    __table_args__ = ({"comment": "智能问数-数据源表"},)

    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="名称")
    code: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, comment="数据源编码"
    )
    type: Mapped[str] = mapped_column(
        String(32), default="postgres", comment="类型: postgres/mysql/sqlite/file/api"
    )
    host: Mapped[str] = mapped_column(String(256), default="", comment="主机")
    port: Mapped[int] = mapped_column(Integer, default=0, comment="端口")
    database: Mapped[str] = mapped_column(String(128), default="", comment="库名/文件名")
    username: Mapped[str] = mapped_column(String(128), default="", comment="用户名")
    password: Mapped[str] = mapped_column(String(512), default="", comment="密码(加密)")
    read_only: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否只读")
    default: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否默认")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    allowed_roles: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="允许访问的角色 code 列表，空=所有"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, default="", comment="备注")


class AiQuerySchemaModel(ModelMixin, UserMixin):
    """数据源已同步的表/字段目录（用于权限白名单与语义注入）。"""

    __tablename__ = "ai_query_schema"
    __table_args__ = ({"comment": "智能问数-数据源 schema 同步表"},)

    datasource: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="数据源编码"
    )
    table_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="表名")
    columns: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="字段 [{name,type,comment,is_sensitive}]"
    )


class AiQueryMetricModel(ModelMixin, UserMixin):
    """语义指标：可参数化 SQL 模板 + 口径。"""

    __tablename__ = "ai_query_metrics"
    __table_args__ = ({"comment": "智能问数-指标表"},)

    datasource: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="数据源编码，system 或 ds:{id}"
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False, comment="指标 key")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="指标名称")
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="口径说明"
    )
    sql_template: Mapped[str] = mapped_column(Text, comment="参数化 SQL 模板")
    params: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="参数定义 [{key,label,type,from}]"
    )
    dimensions: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="维度 [{key,label,field,type}]"
    )
    agg: Mapped[str] = mapped_column(String(32), default="count", comment="聚合方式")
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True, default="", comment="单位")
    permission_tag: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default="", comment="权限标签"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    cache_ttl: Mapped[int] = mapped_column(
        Integer, default=0, comment="缓存秒数，0=不缓存"
    )


class AiQueryDictionaryModel(ModelMixin, UserMixin):
    """业务术语 → 语义(指标/字段) 映射。"""

    __tablename__ = "ai_query_dictionary"
    __table_args__ = ({"comment": "智能问数-术语表"},)

    datasource: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="数据源编码"
    )
    term: Mapped[str] = mapped_column(String(128), nullable=False, comment="术语")
    metric_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, default="", comment="映射指标 key"
    )
    field_path: Mapped[str | None] = mapped_column(
        String(256), nullable=True, default="", comment="映射字段路径"
    )
    type: Mapped[str] = mapped_column(
        String(16), default="term", comment="类型: term/metric/dimension"
    )


class AiQuerySessionModel(ModelMixin, UserMixin):
    """问数会话。"""

    __tablename__ = "ai_query_sessions"
    __table_args__ = ({"comment": "智能问数-会话表"},)

    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="用户ID")
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="租户ID")
    title: Mapped[str] = mapped_column(String(256), default="新会话", comment="标题")
    datasource: Mapped[str] = mapped_column(
        String(64), default="system", comment="当前数据源"
    )


class AiQueryMessageModel(ModelMixin, UserMixin):
    """问答记录（含审计）。"""

    __tablename__ = "ai_query_messages"
    __table_args__ = ({"comment": "智能问数-问答记录表"},)

    session_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="会话ID")
    question: Mapped[str] = mapped_column(Text, comment="用户问句")
    path: Mapped[str] = mapped_column(
        String(16), default="fast", comment="路径: fast/slow"
    )
    datasource: Mapped[str] = mapped_column(String(64), default="system", comment="数据源")
    sql: Mapped[str | None] = mapped_column(Text, nullable=True, default="", comment="执行的SQL")
    columns: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="结果列"
    )
    rows: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="结果行(截断)"
    )
    summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="回复摘要"
    )
    result_rows: Mapped[int] = mapped_column(Integer, default=0, comment="结果行数")
    took_ms: Mapped[int] = mapped_column(Integer, default=0, comment="耗时ms")
    cached: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否命中缓存")
    usage: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="token用量"
    )
    is_error: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否错误")
    feedback: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default="", comment="反馈: up/down/none"
    )
    correct_sql: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="用户修正的 SQL"
    )
