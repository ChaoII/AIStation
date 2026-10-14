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
    filter_rules: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=dict,
        comment="表/字段筛选规则(JSONB)：system_table 前缀/关键词/精确/正则 + audit_fields"
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
    table_comment: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default="",
        comment="表注释——业务库常是中文表名（如「燃煤采购结算主表」），是语义主来源"
    )
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


class AiQueryFewshotModel(ModelMixin, UserMixin):
    """NL2SQL 示例（问题→正确SQL），用于动态 few-shot 引导。"""

    __tablename__ = "ai_query_fewshot"
    __table_args__ = ({"comment": "智能问数-示例库"},)

    datasource: Mapped[str] = mapped_column(
        String(64), default="system", comment="数据源编码"
    )
    question: Mapped[str] = mapped_column(Text, comment="示例问题")
    sql: Mapped[str] = mapped_column(Text, comment="示例正确 SQL")

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")


class AiQueryAssetModel(ModelMixin, UserMixin):
    """问数可查数据资产（表级）：维护中文业务描述 + 是否纳入可查目录。"""

    __tablename__ = "ai_query_assets"
    __table_args__ = ({"comment": "智能问数-表资产目录"},)

    table_name: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, comment="表名"
    )
    alias: Mapped[str | None] = mapped_column(
        String(256), nullable=True, default="", comment="中文别名/表含义"
    )
    domain: Mapped[str | None] = mapped_column(
        String(128), nullable=True, default="", comment="业务域（如：视频/训练/标注）"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="中文业务描述（供检索/模型）"
    )
    business_scenarios: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="业务场景（哪些业务/报表用到此表）"
    )
    included: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否纳入可查目录")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, default="", comment="备注")
    # P0·对象化：是否作为业务对象(Object Type)，主键列/显示名列/图标
    object_enabled: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否业务对象")
    object_key_col: Mapped[str | None] = mapped_column(String(64), default="id", comment="对象主键列")
    object_name_col: Mapped[str | None] = mapped_column(String(64), default="name", comment="对象显示名列")
    object_icon: Mapped[str | None] = mapped_column(String(32), default="el-icon-Box", comment="对象图标")
    # Task3·打标：是否系统/技术表（如 SYS_*、_BAK、定时任务表），过滤规则现算后在同步时落库。
    # 用 Mapped[bool|None]（可空）避免既有 raw INSERT/种子数据缺该列时 NOT NULL 报错。
    is_system: Mapped[bool | None] = mapped_column(Boolean, default=False, comment="是否系统/技术表")


class AiQueryAssetColumnModel(ModelMixin, UserMixin):
    """问数可查数据资产（字段级）：字段业务描述 + 是否纳入。"""

    __tablename__ = "ai_query_asset_columns"
    __table_args__ = ({"comment": "智能问数-字段资产目录"},)

    table_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="表名")
    column_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="字段名")
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="中文业务描述"
    )
    business_scenarios: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="", comment="业务场景（哪些业务/报表需查此字段）"
    )
    related_table: Mapped[str | None] = mapped_column(
        String(128), nullable=True, default="", comment="关联表（联表查询的实体表）"
    )
    related_field: Mapped[str | None] = mapped_column(
        String(128), nullable=True, default="", comment="关联字段（对应关联表的字段）"
    )
    included: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否纳入")
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否敏感字段")
    # Task3·打标：是否审计/技术字段（如 created_time、is_deleted），过滤规则现算后落库。
    # 用 Mapped[bool|None]（可空）避免既有 raw INSERT/种子数据缺该列时 NOT NULL 报错。
    is_audit: Mapped[bool | None] = mapped_column(Boolean, default=False, comment="是否审计/技术字段")
    # Task3·枚举：字段可选值（选项列表），如燃煤类型 [低硫,高硫]
    enum: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, default=list, comment="枚举/选项"
    )


class AiQuerySettingModel(ModelMixin, UserMixin):
    """智能问数全局配置（查询限额/超时等 KV）。"""

    __tablename__ = "ai_query_settings"
    __table_args__ = ({"comment": "智能问数-设置项"},)

    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="配置键")
    value: Mapped[str | None] = mapped_column(Text, nullable=True, default="", comment="配置值")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, default="", comment="说明")


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
        String(16), default="fast", comment="路径: fast(指标模板)/object(对象查询)/slow(NL2SQL)"
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
    # Palantir 审计留痕：本次问数的 grounding（召回表/字段/使用本体/字段级权限命中）
    grounding: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None, comment="Grounding审计(召回表/字段/使用本体/权限命中)"
    )
